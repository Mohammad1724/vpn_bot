# filename: bot/handlers/user_services.py
# -*- coding: utf-8 -*-

import io
import json
import logging
import httpx
import qrcode
from typing import List, Optional

from telegram.ext import ContextTypes
from telegram import Update, Message, InputFile
from telegram.error import BadRequest
from telegram.constants import ParseMode

import database as db
import hiddify_api
from config import ADMIN_ID
from bot import utils
from bot.utils import create_service_info_caption, get_service_status
from bot.ui import nav_row, markup, chunk, btn, confirm_row

try:
    from config import SUBCONVERTER_ENABLED, SUBCONVERTER_DEFAULT_TARGET
except Exception:
    SUBCONVERTER_ENABLED = False
    SUBCONVERTER_DEFAULT_TARGET = "v2ray"

# برای ساخت fallback لینک هر نود درصورت نبود sub_link
try:
    from config import SUB_PATH as CFG_SUB_PATH
except Exception:
    CFG_SUB_PATH = "sub"

logger = logging.getLogger(__name__)


def _link_label(link_type: str) -> str:
    lt = utils.normalize_link_type(link_type)
    return {
        "sub": "V2Ray (sub)",
        "auto": "هوشمند (Auto)",
        "sub64": "Base64 (sub64)",
        "singbox": "SingBox",
        "xray": "Xray",
        "clash": "Clash",
        "clashmeta": "Clash Meta",
        "unified": "لینک واحد (Subconverter)",
    }.get(lt, "V2Ray (sub)")


def _compute_base_link(service: dict, user_uuid: str) -> str:
    # لینک اصلی/تجمیعی روی دامنه/مسیر اصلی
    base_main = utils.build_subscription_url(user_uuid)
    if isinstance(base_main, str) and base_main.strip():
        return base_main.strip().rstrip("/")

    # اگر در رکورد سرویس sub_link داشت
    sub_link = (service or {}).get("sub_link")
    if isinstance(sub_link, str) and sub_link.strip():
        return sub_link.strip().rstrip("/")

    # در نهایت لینک اختصاصی همان نود رکورد سرویس
    return utils.build_subscription_url(user_uuid, server_name=(service or {}).get("server_name")).rstrip("/")


def _endpoint_to_base_link(ep: dict, service: dict) -> Optional[str]:
    """
    تولید لینک sub برای هر نود endpoint با اولویت:
    1) ep.sub_link یا ep.sub_url
    2) ساختن با panel_domain/domain/host + sub_path (+ sub_uuid)
    3) ساختن با server_name از روی تنظیمات SERVERS
    """
    # 1) اگر مستقیم لینک ذخیره‌شده داریم
    direct = (ep.get("sub_link") or ep.get("sub_url") or "").strip().rstrip("/")
    if direct:
        return direct

    ep_uuid = (ep.get("sub_uuid") or "").strip() or service.get("sub_uuid")
    if not ep_uuid:
        return None

    # 2) اگر دامین نود داخل endpoint هست، مستقیم می‌سازیم
    domain = (ep.get("panel_domain") or ep.get("domain") or ep.get("host") or "").strip()
    if not domain and isinstance(ep.get("sub_domains"), list) and ep["sub_domains"]:
        domain = str(ep["sub_domains"][0]).strip()
    sub_path = (ep.get("sub_path") or CFG_SUB_PATH or "sub").strip().strip("/")

    if domain:
        return f"https://{domain}/{sub_path}/{ep_uuid}".rstrip("/")

    # 3) در غیر این صورت با server_name می‌سازیم (از روی SERVERS در config)
    server_name = (ep.get("server_name") or service.get("server_name"))
    try:
        built = utils.build_subscription_url(ep_uuid, server_name=server_name)
        if isinstance(built, str) and built.strip():
            return built.strip().rstrip("/")
    except Exception:
        pass
    return None


def _collect_subscription_bases(service: dict) -> List[str]:
    """
    جمع‌آوری تمام لینک‌های قابل ادغام برای این سرویس:
    - لینک اصلی (تجمیعی/گروهی)
    - لینک تک‌تک نودها (از endpointها) با فالبک‌های مختلف
    """
    bases: List[str] = []

    # لینک اصلی
    main_base = _compute_base_link(service, service["sub_uuid"])
    if main_base:
        bases.append(main_base)

    # لینک‌های نودها
    try:
        endpoints = db.list_service_endpoints(service["service_id"]) or []
        for ep in endpoints:
            ep_link = _endpoint_to_base_link(ep, service)
            if ep_link:
                bases.append(ep_link)
    except Exception as e:
        logger.debug("list_service_endpoints failed for service %s: %s", service.get("service_id"), e)

    # حذف تکراری‌ها با حفظ ترتیب
    seen = set()
    dedup: List[str] = []
    for b in bases:
        if not b:
            continue
        if b not in seen:
            dedup.append(b)
            seen.add(b)
    return dedup


def _build_unified_link_for_type(service: dict, link_type: str) -> str | None:
    """
    اگر Subconverter فعال باشد و حداقل دو منبع داشته باشیم، لینک واحد تولید می‌کند.
    """
    if not SUBCONVERTER_ENABLED:
        return None

    bases = _collect_subscription_bases(service)
    if not bases or len(bases) < 2:
        return None

    # تعیین target
    try:
        target = utils.link_type_to_subconverter_target(link_type)
    except Exception:
        target = None
    if not target or link_type == "unified":
        target = SUBCONVERTER_DEFAULT_TARGET or "v2ray"

    return utils.build_subconverter_link(bases, target=target)


def _get_default_link_type() -> str:
    """
    نوع لینک انتخابی ادمین را از تنظیمات می‌خواند؛
    کلید درست طبق settings.py: default_sub_link_type
    """
    try:
        v = db.get_setting("default_sub_link_type")
        if v:
            return utils.normalize_link_type(str(v))
    except Exception:
        pass
    return "sub"


async def list_my_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    services = db.get_user_services(user_id)
    if not services:
        await context.bot.send_message(chat_id=user_id, text="شما در حال حاضر هیچ سرویس فعالی ندارید.")
        return
    keyboard = [[btn(f"⚙️ {s['name'] or 'سرویس بدون نام'}", f"view_service_{s['service_id']}")] for s in services]
    keyboard.append(nav_row(home_cb="home_menu"))
    await context.bot.send_message(
        chat_id=user_id,
        text="لطفاً سرویسی که می‌خواهید مدیریتش کنید را انتخاب نمایید:",
        reply_markup=markup(keyboard)
    )


async def view_service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    service_id = int(q.data.split('_')[-1])
    if q.message:
        try:
            await q.message.delete()
        except BadRequest:
            pass
    msg = await context.bot.send_message(chat_id=q.from_user.id, text="در حال دریافت اطلاعات سرویس... ⏳")
    await send_service_details(context, q.from_user.id, service_id, original_message=msg, is_from_menu=True)


async def send_service_details(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    service_id: int,
    original_message: Message | None = None,
    is_from_menu: bool = False,
    minimal: bool = False
):
    service = db.get_service(service_id)
    if not service:
        text = "❌ سرویس مورد نظر یافت نشد."
        target = original_message.edit_text if original_message else context.bot.send_message
        await target(chat_id=chat_id, text=text)
        return
    try:
        info = await hiddify_api.get_user_info(service['sub_uuid'], server_name=service.get("server_name"))
        if not info or (isinstance(info, dict) and info.get('_not_found')):
            kb = [
                [btn("🗑️ حذف سرویس از ربات", f"delete_service_{service['service_id']}")],
                [btn("🔄 تلاش مجدد", f"refresh_{service['service_id']}")],
                nav_row(back_cb="back_to_services", home_cb="home_menu")
            ]
            text = "❌ اطلاعات این سرویس در پنل یافت نشد. احتمالاً حذف شده است.\nمی‌خواهید این سرویس از ربات هم حذف شود؟"
            target = original_message.edit_text if original_message else context.bot.send_message
            await target(chat_id=chat_id, text=text, reply_markup=markup(kb))
            return

        # نام کانفیگ برای ?name=
        config_name = (info.get('name', 'config') if isinstance(info, dict) else 'config') or 'config'
        safe_name = config_name.replace(' ', '_')

        # تلاش برای ساخت لینک واحد پیش‌فرض (اگر حداقل دو منبع داریم)
        unified_default_link = None
        if SUBCONVERTER_ENABLED:
            try:
                bases = _collect_subscription_bases(service)
                if bases and len(bases) > 1:
                    unified_default_link = utils.build_subconverter_link(bases)
            except Exception as e:
                logger.debug("build unified_default_link failed for service %s: %s", service_id, e)

        # اعمال نوع لینک انتخابی ادمین روی لینکی که در کپشن نمایش داده می‌شود
        admin_default_type = _get_default_link_type()
        preferred_url = None
        if admin_default_type == "unified":
            preferred_url = _build_unified_link_for_type(service, "unified") if SUBCONVERTER_ENABLED else None
        else:
            base_link = _compute_base_link(service, service['sub_uuid'])
            t = utils.normalize_link_type(admin_default_type)
            if t == "sub":
                preferred_url = base_link
            else:
                url_link_type = t.replace('clashmeta', 'clash-meta')
                preferred_url = f"{base_link}/{url_link_type}/?name={safe_name}"

        # اگر به هر دلیل preferred_url نداشتیم، از unified_default_link یا base استفاده کن
        override_url = preferred_url or unified_default_link or _compute_base_link(service, service['sub_uuid'])

        caption = utils.create_service_info_caption(info, service_db_record=service, override_sub_url=override_url)

        keyboard_rows = []
        if not minimal:
            if unified_default_link:
                keyboard_rows.append([btn("🔗 لینک واحد (پیشنهادی)", f"getlink_unified_{service['sub_uuid']}")])
            keyboard_rows.append([
                btn("🔄 به‌روزرسانی اطلاعات", f"refresh_{service['service_id']}"),
                btn("🔗 لینک‌های بیشتر", f"more_links_{service['sub_uuid']}"),
            ])
            if plan := (db.get_plan(service['plan_id']) if service.get('plan_id') else None):
                keyboard_rows.append([btn(f"⏳ تمدید سرویس ({int(plan['price']):,} تومان)", f"renew_{service['service_id']}")])
            keyboard_rows.append([btn("🗑️ حذف سرویس", f"delete_service_{service['service_id']}")])
            if is_from_menu:
                keyboard_rows.append(nav_row(back_cb="back_to_services", home_cb="home_menu"))

        if original_message:
            try:
                await original_message.delete()
            except BadRequest:
                pass
        await context.bot.send_message(
            chat_id=chat_id, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=markup(keyboard_rows)
        )
    except Exception as e:
        logger.error("send_service_details error for service_id %s: %s", service_id, e, exc_info=True)
        text = "❌ خطا در دریافت اطلاعات سرویس. لطفاً بعداً دوباره تلاش کنید."
        target = original_message.edit_text if original_message else context.bot.send_message
        await target(chat_id=chat_id, text=text)


async def more_links_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uuid = q.data.split('_')[-1]
    service = db.get_service_by_uuid(uuid)
    if not service:
        await q.edit_message_text("سرویس یافت نشد.")
        return
    await show_link_options_menu(q.message, uuid, service['service_id'], is_edit=True, context=context)


async def show_link_options_menu(message: Message, user_uuid: str, service_id: int, is_edit: bool = True, context: ContextTypes.DEFAULT_TYPE = None):
    buttons = [
        btn("V2ray (sub)", f"getlink_sub_{user_uuid}"),
        btn("هوشمند (Auto)", f"getlink_auto_{user_uuid}"),
        btn("Base64 (sub64)", f"getlink_sub64_{user_uuid}"),
        btn("SingBox", f"getlink_singbox_{user_uuid}"),
        btn("Xray", f"getlink_xray_{user_uuid}"),
        btn("Clash", f"getlink_clash_{user_uuid}"),
        btn("Clash Meta", f"getlink_clashmeta_{user_uuid}"),
        btn("📄 کانفیگ‌های تکی", f"getlink_full_{user_uuid}"),
    ]
    rows = chunk(buttons, cols=2)
    try:
        service = db.get_service_by_uuid(user_uuid)
        bases = _collect_subscription_bases(service)
        if SUBCONVERTER_ENABLED and len(bases) >= 2:
            rows.insert(0, [btn("🔗 لینک واحد (پیشنهادی)", f"getlink_unified_{user_uuid}")])
    except Exception:
        pass
    rows.append(nav_row(back_cb=f"refresh_{service_id}", home_cb="home_menu"))
    text = "لطفاً نوع لینک اشتراک مورد نظر را انتخاب کنید:"
    try:
        if is_edit:
            if message.photo:
                await message.delete()
                await context.bot.send_message(chat_id=message.chat_id, text=text, reply_markup=markup(rows))
            else:
                await message.edit_text(text, reply_markup=markup(rows))
        else:
            await message.reply_text(text, reply_markup=markup(rows))
    except BadRequest as e:
        if "message is not modified" not in str(e):
            logger.error("show_link_options_menu error: %s", e)


async def get_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split('_')
    link_type, user_uuid = parts[1], parts[2]
    service = db.get_service_by_uuid(user_uuid)
    if not service:
        await q.edit_message_text("❌ سرویس یافت نشد."); return

    info = await hiddify_api.get_user_info(user_uuid, server_name=service.get("server_name"))
    config_name = (info.get('name', 'config') if isinstance(info, dict) else 'config') or 'config'
    safe_name = config_name.replace(' ', '_')

    if link_type == "full":
        try:
            await q.edit_message_text("در حال دریافت کانفیگ‌های تکی... ⏳")
            full_link = f"{_compute_base_link(service, user_uuid)}/all.txt"
            async with httpx.AsyncClient(timeout=20) as c:
                resp = await c.get(full_link)
                resp.raise_for_status()
            await q.message.delete()
            await context.bot.send_document(
                chat_id=q.from_user.id,
                document=InputFile(io.BytesIO(resp.content), filename=f"{safe_name}_configs.txt"),
                caption="📄 کانفیگ‌های تکی شما به صورت فایل ارسال شد.",
                reply_markup=markup([nav_row(back_cb=f"more_links_{user_uuid}", home_cb="home_menu")])
            )
        except Exception as e:
            logger.error("Failed to fetch/send full configs: %s", e, exc_info=True)
            await q.edit_message_text("❌ دریافت کانفیگ‌های تکی با خطا مواجه شد.")
        return

    unified_link = _build_unified_link_for_type(service, link_type) if SUBCONVERTER_ENABLED else None

    # دیباگ برای ادمین: ببینیم چه سورس‌هایی شناسایی شده
    if q.from_user.id == ADMIN_ID:
        try:
            sources_dbg = _collect_subscription_bases(service)
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"DEBUG unified={bool(unified_link)} | sources={json.dumps(sources_dbg, ensure_ascii=False)}"
            )
        except Exception:
            pass

    if unified_link:
        final_link = unified_link
    else:
        base_link = _compute_base_link(service, user_uuid)
        url_link_type = utils.normalize_link_type(link_type).replace('clashmeta', 'clash-meta')
        final_link = f"{base_link}/{url_link_type}/?name={safe_name}"

    qr_bio = utils.make_qr_bytes(final_link)
    caption = f"نام کانفیگ: **{config_name}**\nنوع لینک: **{_link_label(link_type)}**\n\n`{final_link}`"
    try:
        await q.message.delete()
    except BadRequest:
        pass
    await context.bot.send_photo(
        chat_id=q.message.chat_id, photo=qr_bio, caption=caption, parse_mode="Markdown",
        reply_markup=markup([nav_row(back_cb=f"more_links_{user_uuid}", home_cb="home_menu")])
    )


async def refresh_service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    service_id = int(q.data.split('_')[1])
    service = db.get_service(service_id)

    if not service or service['user_id'] != q.from_user.id:
        await q.answer("خطا: این سرویس متعلق به شما نیست.", show_alert=True); return

    try:
        await q.message.delete()
    except BadRequest:
        pass
    msg = await context.bot.send_message(chat_id=q.from_user.id, text="در حال به‌روزرسانی اطلاعات...")
    if q.from_user.id == ADMIN_ID:
        try:
            info = await hiddify_api.get_user_info(service['sub_uuid'], server_name=service.get("server_name"))
            if info:
                await q.from_user.send_message(f"-- DEBUG INFO --\n<pre>{json.dumps(info, indent=2, ensure_ascii=False)}</pre>", parse_mode="HTML")
        except Exception as e:
            await q.from_user.send_message(f"Debug error: {e}")
    await send_service_details(context, q.from_user.id, service_id, original_message=msg, is_from_menu=True)


async def back_to_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        await q.message.delete()
    except BadRequest:
        pass
    await list_my_services(update, context)


async def delete_service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    try:
        service_id = int(data.split('_')[-1])
    except Exception:
        await q.edit_message_text("❌ ورودی نامعتبر."); return

    service = db.get_service(service_id)
    if not service or service['user_id'] != q.from_user.id:
        await q.edit_message_text("❌ سرویس یافت نشد یا متعلق به شما نیست."); return

    if data.startswith("delete_service_cancel_"):
        await send_service_details(context, q.from_user.id, service_id, original_message=q.message, is_from_menu=True); return

    if not data.startswith("delete_service_confirm_"):
        kb = markup([confirm_row(f"delete_service_confirm_{service_id}", f"delete_service_cancel_{service_id}")])
        await q.edit_message_text(
            "آیا از حذف این سرویس مطمئن هستید؟ این عمل سرویس را از پنل اصلی و تمام نودها حذف می‌کند و قابل بازگشت نیست.",
            reply_markup=kb
        ); return

    try:
        await q.edit_message_text("در حال حذف سرویس از پنل... ⏳")
    except BadRequest:
        pass
    try:
        success = await hiddify_api.delete_user_from_panel(service['sub_uuid'], server_name=service.get("server_name"))
        if not success:
            probe = await hiddify_api.get_user_info(service['sub_uuid'], server_name=service.get("server_name"))
            if isinstance(probe, dict) and probe.get("_not_found"):
                success = True
        if not success:
            await q.edit_message_text("❌ حذف سرویس از پنل با خطا مواجه شد."); return

        endpoints = db.list_service_endpoints(service_id) or []
        for ep in endpoints:
            if ep_uuid := (ep.get("sub_uuid") or "").strip():
                await hiddify_api.delete_user_from_panel(ep_uuid, server_name=ep.get("server_name"))
        db.delete_service(service_id)

        await q.edit_message_text("✅ سرویس با موفقیت از پنل و ربات حذف شد.")
        kb = markup([nav_row(back_cb="back_to_services", home_cb="home_menu")])
        await context.bot.send_message(chat_id=q.from_user.id, text="عملیات حذف کامل شد.", reply_markup=kb)
    except Exception as e:
        logger.error("Delete service %s failed: %s", service_id, e, exc_info=True)
        await q.edit_message_text("❌ حذف سرویس با خطای ناشناخته مواجه شد.")


async def renew_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    try:
        await q.message.delete()
    except BadRequest:
        pass

    service_id = int(q.data.split('_')[1])
    user_id = q.from_user.id
    service = db.get_service(service_id)
    if not service:
        await context.bot.send_message(chat_id=user_id, text="❌ سرویس نامعتبر است."); return
    plan = db.get_plan(service['plan_id']) if service.get('plan_id') else None
    if not plan:
        await context.bot.send_message(chat_id=user_id, text="❌ پلن تمدید یافت نشد."); return
    user = db.get_or_create_user(user_id)
    if user['balance'] < plan['price']:
        await context.bot.send_message(chat_id=user_id, text=f"موجودی کافی نیست! (نیاز به {int(plan['price']):,} تومان)"); return
    info = await hiddify_api.get_user_info(service['sub_uuid'], server_name=service.get("server_name"))
    if not info:
        await context.bot.send_message(chat_id=user_id, text="❌ دریافت اطلاعات از پنل ممکن نیست."); return

    usage_limit = float(info.get('usage_limit_GB', 0)); current_usage = float(info.get('current_usage_GB', 0))
    remaining_gb = max(usage_limit - current_usage, 0.0)
    _, jalali_exp, _ = utils.get_service_status(info)
    context.user_data['renewal_service_id'] = service_id
    context.user_data['renewal_plan_id'] = plan['plan_id']
    text = f"""⚠️ هشدار تمدید
با تمدید، اعتبار زمانی و حجمی باقیمانده شما ریست می‌شود.
وضعیت فعلی: {jalali_exp} | {remaining_gb:.2f} گیگ باقیمانده
مشخصات تمدید: {plan['days']} روز | {plan['gb']} گیگ | {int(plan['price']):,} تومان
آیا تایید می‌کنید؟""".strip()
    kb = [confirm_row("confirmrenew", "cancelrenew"), nav_row(f"refresh_{service_id}", "home_menu")]
    await context.bot.send_message(chat_id=user_id, text=text, reply_markup=markup(kb), parse_mode=ParseMode.MARKDOWN)


async def confirm_renewal_callback(update: Update, Context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    await proceed_with_renewal(update, Context, original_message=q.message)


async def proceed_with_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE, original_message=None):
    q = update.callback_query; user_id = q.from_user.id if q else update.effective_user.id
    service_id, plan_id = context.user_data.get('renewal_service_id'), context.user_data.get('renewal_plan_id')
    if not service_id or not plan_id:
        await _send_renewal_error(original_message, "❌ خطای داخلی: اطلاعات تمدید یافت نشد."); return
    if original_message:
        await original_message.edit_text("در حال ارسال درخواست تمدید... ⏳")
    service, plan = db.get_service(service_id), db.get_plan(plan_id)
    if not service or not plan or service['user_id'] != user_id:
        await _send_renewal_error(original_message, "❌ اطلاعات سرویس یا پلن نامعتبر است."); return
    txn_id = db.initiate_renewal_transaction(user_id, service_id, plan_id)
    if not txn_id:
        await _send_renewal_error(original_message, "❌ مشکلی در شروع تمدید پیش آمد (مثلاً عدم موجودی)."); return
    try:
        new_info = await hiddify_api.renew_user_subscription(
            user_uuid=service['sub_uuid'], plan_days=plan['days'], plan_gb=plan['gb'], server_name=service.get("server_name")
        )
        if not new_info:
            raise ValueError("Invalid API response")
        endpoints = db.list_service_endpoints(service_id) or []
        for ep in endpoints:
            if ep_uuid := (ep.get("sub_uuid") or "").strip():
                await hiddify_api.renew_user_subscription(
                    user_uuid=ep_uuid, plan_days=plan['days'], plan_gb=plan['gb'], server_name=ep.get("server_name")
                )
        db.finalize_renewal_transaction(txn_id, plan_id)
        if original_message:
            await original_message.edit_text("✅ سرویس با موفقیت تمدید شد!")
        await send_service_details(context, user_id, service_id, original_message=original_message, is_from_menu=True)
    except Exception as e:
        logger.error(f"Service renewal failed: {e}", exc_info=True)
        db.cancel_renewal_transaction(txn_id)
        await _send_renewal_error(original_message, "❌ خطا در تمدید سرویس. به پشتیبانی اطلاع دهید.")
    context.user_data.clear()


async def _send_renewal_error(message, error_text: str):
    if message:
        try:
            await message.edit_text(error_text)
        except Exception:
            pass


async def cancel_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    await q.edit_message_text("عملیات تمدید لغو شد.")