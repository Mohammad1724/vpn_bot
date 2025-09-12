# filename: bot/handlers/user_services.py
# -*- coding: utf-8 -*-

import io
import json
import logging
import httpx
from typing import List, Optional
from urllib.parse import quote_plus, urlsplit, urlunsplit

from telegram.ext import ContextTypes
from telegram import Update, Message, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.constants import ParseMode

import database as db
import hiddify_api
from bot import utils
from bot.ui import nav_row, markup, chunk, btn, confirm_row

try:
    from config import ADMIN_ID, HIDDIFY_API_VERIFY_SSL
except ImportError:
    ADMIN_ID = None
    HIDDIFY_API_VERIFY_SSL = True

logger = logging.getLogger(__name__)


def _link_label(link_type: str) -> str:
    lt = utils.normalize_link_type(link_type)
    return {
        "sub": "V2Ray (پیش‌فرض)",
        "singbox": "SingBox",
        "clash": "Clash",
        "clashmeta": "Clash Meta",
    }.get(lt, "V2Ray (sub)")


def _strip_qf_and_sub(url: str) -> str:
    pr = urlsplit(url)
    path = pr.path
    if path.endswith('/sub/'):
        path = path[:-5]
    elif path.endswith('/sub'):
        path = path[:-4]
    return urlunsplit((pr.scheme, pr.netloc, path.rstrip('/'), '', ''))


def _same_user(a, b) -> bool:
    """مقایسه امن شناسه کاربر برای جلوگیری از ناسازگاری str/int."""
    try:
        return int(a) == int(b)
    except Exception:
        return str(a) == str(b)


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
    is_from_menu: bool = False
):
    service = db.get_service(service_id)
    if not service:
        text = "❌ سرویس مورد نظر یافت نشد."
        if original_message:
            await original_message.edit_text(text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)
        return

    # چک مالکیت امن
    if not _same_user(service['user_id'], chat_id):
        text = "❌ این سرویس متعلق به شما نیست."
        if original_message:
            try:
                await original_message.edit_text(text)
            except BadRequest:
                pass
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)
        return

    try:
        info = await hiddify_api.get_user_info(service['sub_uuid'])
        if not info or (isinstance(info, dict) and info.get('_not_found')):
            kb = [
                [btn("🗑️ حذف سرویس از ربات", f"delete_service_{service['service_id']}")],
                [btn("🔄 تلاش مجدد", f"refresh_{service['service_id']}")],
                nav_row(back_cb="back_to_services", home_cb="home_menu")
            ]
            text = "❌ اطلاعات این سرویس در پنل یافت نشد. احتمالاً حذف شده است.\nمی‌خواهید این سرویس از ربات هم حذف شود؟"
            if original_message:
                await original_message.edit_text(text, reply_markup=markup(kb))
            else:
                await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup(kb))
            return

        config_name = (info.get('name', 'config') if isinstance(info, dict) else 'config') or 'config'

        # انتخاب دامنه بر اساس تنظیمات ادمین و نوع پلن (حجمی/نامحدود)
        plan = db.get_plan(service['plan_id']) if service.get('plan_id') else None
        plan_gb = int(plan['gb']) if plan and 'gb' in plan else None
        preferred_url = utils.build_subscription_url(service['sub_uuid'], name=config_name, plan_gb=plan_gb)

        caption = utils.create_service_info_caption(info, service_db_record=service, title="اطلاعات سرویس شما", override_sub_url=preferred_url)
        keyboard_rows = [
            [
                btn("🔄 به‌روزرسانی اطلاعات", f"refresh_{service['service_id']}"),
                btn("🔗 لینک‌های بیشتر", f"more_links_{service['sub_uuid']}"),
            ],
        ]
        if plan:
            keyboard_rows.append([btn(f"⏳ تمدید سرویس ({int(plan['price']):,} تومان)", f"renew_{service['service_id']}")])
        keyboard_rows.append([btn("🗑️ حذف سرویس", f"delete_service_{service['service_id']}")])
        if is_from_menu:
            keyboard_rows.append(nav_row(back_cb="back_to_services", home_cb="home_menu"))

        qr_bio = utils.make_qr_bytes(preferred_url)
        if original_message:
            try:
                await original_message.delete()
            except BadRequest:
                pass

        await context.bot.send_photo(
            chat_id=chat_id,
            photo=InputFile(qr_bio),
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=markup(keyboard_rows)
        )
    except Exception as e:
        logger.error("send_service_details error for service_id %s: %s", service_id, e, exc_info=True)
        text = "❌ خطا در دریافت اطلاعات سرویس. لطفاً بعداً دوباره تلاش کنید."
        if original_message:
            await original_message.edit_text(text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)


async def more_links_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uuid = q.data.split('_')[-1]
    service = db.get_service_by_uuid(uuid)
    if not service or not _same_user(service['user_id'], q.from_user.id):
        await q.edit_message_text("❌ سرویس یافت نشد یا متعلق به شما نیست.")
        return
    await show_link_options_menu(q.message, uuid, service['service_id'], is_edit=True, context=context)


async def show_link_options_menu(message: Message, user_uuid: str, service_id: int, is_edit: bool = True, context: ContextTypes.DEFAULT_TYPE = None):
    buttons = [
        btn("V2ray (sub)", f"getlink_sub_{user_uuid}"),
        btn("SingBox", f"getlink_singbox_{user_uuid}"),
        btn("Clash", f"getlink_clash_{user_uuid}"),
        btn("Clash Meta", f"getlink_clashmeta_{user_uuid}"),
        btn("📄 کانفیگ‌های تکی", f"getlink_full_{user_uuid}"),
    ]
    rows = chunk(buttons, cols=2)
    rows.append(nav_row(back_cb=f"refresh_{service_id}", home_cb="home_menu"))
    text = "لطفاً نوع لینک اشتراک مورد نظر را انتخاب کنید:"
    try:
        if is_edit:
            await message.delete()
            await context.bot.send_message(chat_id=message.chat_id, text=text, reply_markup=markup(rows))
        else:
            await message.reply_text(text, reply_markup=markup(rows))
    except BadRequest as e:
        if "message to delete not found" not in str(e):
            logger.error("show_link_options_menu error: %s", e)


async def get_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split('_')
    link_type, user_uuid = parts[1], parts[2]
    service = db.get_service_by_uuid(user_uuid)
    if not service or not _same_user(service['user_id'], q.from_user.id):
        await q.edit_message_text("❌ سرویس یافت نشد یا متعلق به شما نیست.")
        return

    info = await hiddify_api.get_user_info(user_uuid)
    config_name = (info.get('name', 'config') if isinstance(info, dict) else 'config') or 'config'

    # حالت full: مسیر …/<uuid>/all.txt (بدون suffix نوع لینک)
    if link_type == "full":
        try:
            await q.edit_message_text("در حال دریافت کانفیگ‌های تکی... ⏳")
            base_user_path = _strip_qf_and_sub(service['sub_link'])
            full_url = f"{base_user_path}/all.txt"

            verify_ssl = HIDDIFY_API_VERIFY_SSL
            if not isinstance(verify_ssl, bool):
                verify_ssl = str(verify_ssl).strip().lower() in ("1", "true", "yes", "on")

            async with httpx.AsyncClient(timeout=20, verify=verify_ssl, follow_redirects=True) as c:
                resp = await c.get(full_url)
                resp.raise_for_status()
            try:
                await q.message.delete()
            except BadRequest:
                pass
            await context.bot.send_document(
                chat_id=q.from_user.id,
                document=InputFile(io.BytesIO(resp.content), filename=f"{quote_plus(config_name)}_configs.txt"),
                caption="📄 کانفیگ‌های تکی شما به صورت فایل ارسال شد.",
                reply_markup=markup([nav_row(back_cb=f"more_links_{user_uuid}", home_cb="home_menu")])
            )
        except Exception as e:
            logger.error("Failed to fetch/send full configs: %s", e, exc_info=True)
            await q.edit_message_text("❌ دریافت کانفیگ‌های تکی با خطا مواجه شد.")
        return

    # سایر انواع لینک: بر اساس تنظیمات ادمین + نوع پلن
    plan = db.get_plan(service['plan_id']) if service.get('plan_id') else None
    plan_gb = int(plan['gb']) if plan and 'gb' in plan else None
    final_link = utils.build_subscription_url(user_uuid, link_type=link_type, name=config_name, plan_gb=plan_gb)

    try:
        await q.message.delete()
    except BadRequest:
        pass

    safe_link = str(final_link).replace('`', '\\`')  # جلوگیری از شکست Markdown
    text = f"🔗 *لینک {_link_label(link_type)}*\n`{safe_link}`\n\n👆 با یک لمس روی لینک بالا، کپی می‌شود."

    kb = markup([nav_row(back_cb=f"more_links_{user_uuid}", home_cb="home_menu")])

    await context.bot.send_message(
        chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN
    )


async def refresh_service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    service_id = int(q.data.split('_')[1])
    service = db.get_service(service_id)

    if not service or not _same_user(service['user_id'], q.from_user.id):
        await q.answer("خطا: این سرویس متعلق به شما نیست.", show_alert=True)
        return

    try:
        await q.message.delete()
    except BadRequest:
        pass
    msg = await context.bot.send_message(chat_id=q.from_user.id, text="در حال به‌روزرسانی اطلاعات...")
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
        await q.edit_message_text("❌ ورودی نامعتبر.")
        return

    service = db.get_service(service_id)
    if not service or not _same_user(service['user_id'], q.from_user.id):
        await q.edit_message_text("❌ سرویس یافت نشد یا متعلق به شما نیست.")
        return

    if data.startswith("delete_service_cancel_"):
        await send_service_details(context, q.from_user.id, service_id, original_message=q.message, is_from_menu=True)
        return

    if not data.startswith("delete_service_confirm_"):
        try:
            await q.message.delete()
        except BadRequest:
            pass
        kb = markup([confirm_row(f"delete_service_confirm_{service_id}", f"delete_service_cancel_{service_id}")])
        await context.bot.send_message(
            chat_id=q.from_user.id,
            text="آیا از حذف این سرویس مطمئن هستید؟ این عمل سرویس را از پنل اصلی حذف می‌کند و قابل بازگشت نیست.",
            reply_markup=kb
        )
        return

    try:
        await q.edit_message_text("در حال حذف سرویس از پنل... ⏳")
    except BadRequest:
        pass
    try:
        success = await hiddify_api.delete_user_from_panel(service['sub_uuid'])
        if not success:
            probe = await hiddify_api.get_user_info(service['sub_uuid'])
            if isinstance(probe, dict) and probe.get("_not_found"):
                success = True
        if not success:
            await q.edit_message_text("❌ حذف سرویس از پنل با خطا مواجه شد.")
            return
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
    if not service or not _same_user(service['user_id'], user_id):
        await context.bot.send_message(chat_id=user_id, text="❌ سرویس نامعتبر است یا متعلق به شما نیست.")
        return
    plan = db.get_plan(service['plan_id']) if service.get('plan_id') else None
    if not plan:
        await context.bot.send_message(chat_id=user_id, text="❌ پلن تمدید یافت نشد.")
        return
    user = db.get_or_create_user(user_id)
    if user['balance'] < plan['price']:
        await context.bot.send_message(chat_id=user_id, text=f"موجودی کافی نیست! (نیاز به {int(plan['price']):,} تومان)")
        return
    info = await hiddify_api.get_user_info(service['sub_uuid'])
    if not info:
        await context.bot.send_message(chat_id=user_id, text="❌ دریافت اطلاعات از پنل ممکن نیست.")
        return

    usage_limit = float(info.get('usage_limit_GB') or 0)
    current_usage = float(info.get('current_usage_GB') or 0)
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


async def confirm_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await proceed_with_renewal(update, context, original_message=q.message)


async def proceed_with_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE, original_message=None):
    q = update.callback_query
    user_id = q.from_user.id if q else update.effective_user.id

    service_id = context.user_data.get('renewal_service_id')
    plan_id = context.user_data.get('renewal_plan_id')
    if not service_id or not plan_id:
        await _send_renewal_error(original_message, "❌ خطای داخلی: اطلاعات تمدید یافت نشد.")
        return

    if original_message:
        try:
            await original_message.edit_text("در حال تمدید سرویس در پنل... ⏳")
        except BadRequest:
            pass

    service = db.get_service(service_id)
    plan = db.get_plan(plan_id)
    if not service or not plan or not _same_user(service['user_id'], user_id):
        await _send_renewal_error(original_message, "❌ اطلاعات سرویس یا پلن نامعتبر است.")
        return

    logger.info(
        "Renewal Attempt: user=%s, service=%s, plan=%s, uuid=%s, days=%s, gb=%s",
        user_id, service_id, plan_id, service['sub_uuid'], plan['days'], plan['gb']
    )

    txn_id = db.initiate_renewal_transaction(user_id, service_id, plan_id)
    if not txn_id:
        await _send_renewal_error(original_message, "❌ مشکلی در شروع تمدید پیش آمد (مثلاً عدم موجودی).")
        return

    try:
        new_info = await hiddify_api.renew_user_subscription(
            user_uuid=service['sub_uuid'],
            plan_days=int(plan['days']),
            plan_gb=float(plan['gb'])
        )

        if not new_info:
            logger.error("Renewal failed for UUID %s: Panel verification failed.", service['sub_uuid'])
            raise ValueError("Panel verification failed")

        db.finalize_renewal_transaction(txn_id, plan_id)

        if original_message:
            try:
                await original_message.edit_text("✅ سرویس با موفقیت تمدید شد!")
            except BadRequest:
                pass

        await send_service_details(context, user_id, service_id, original_message=original_message, is_from_menu=True)

    except Exception as e:
        logger.error("Service renewal failed for UUID %s: %s", service['sub_uuid'], e, exc_info=True)
        db.cancel_renewal_transaction(txn_id)
        await _send_renewal_error(original_message, "❌ تمدید در پنل اعمال نشد. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.")
    finally:
        context.user_data.pop('renewal_service_id', None)
        context.user_data.pop('renewal_plan_id', None)


async def _send_renewal_error(message, error_text: str):
    if message:
        try:
            await message.edit_text(error_text)
        except Exception:
            pass


async def cancel_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("عملیات تمدید لغو شد.")