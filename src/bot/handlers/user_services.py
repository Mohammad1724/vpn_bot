# -*- coding: utf-8 -*-

import io
import json
import logging
import httpx
import qrcode
from telegram.ext import ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, InputFile
from telegram.error import BadRequest
from telegram.constants import ParseMode

import database as db
import hiddify_api
from config import ADMIN_ID
from bot.utils import get_domain_for_plan, create_service_info_message, get_service_status

logger = logging.getLogger(__name__)


def _normalize_link_type(t: str) -> str:
    return (t or "sub").strip().lower().replace("clash-meta", "clashmeta")


def _link_label(link_type: str) -> str:
    lt = _normalize_link_type(link_type)
    return {
        "sub": "V2Ray (sub)",
        "auto": "هوشمند (Auto)",
        "sub64": "Base64 (sub64)",
        "singbox": "SingBox",
        "xray": "Xray",
        "clash": "Clash",
        "clashmeta": "Clash Meta",
    }.get(lt, "V2Ray (sub)")


async def list_my_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    services = db.get_user_services(user_id)
    if not services:
        await context.bot.send_message(chat_id=user_id, text="شما در حال حاضر هیچ سرویس فعالی ندارید.")
        return
    keyboard = [
        [InlineKeyboardButton(f"⚙️ {s['name'] or 'سرویس بدون نام'}", callback_data=f"view_service_{s['service_id']}")]
        for s in services
    ]
    await context.bot.send_message(
        chat_id=user_id,
        text="لطفاً سرویسی که می‌خواهید مدیریتش کنید را انتخاب نمایید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
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
        if original_message:
            try:
                await original_message.edit_text(text)
            except BadRequest:
                await context.bot.send_message(chat_id=chat_id, text=text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)
        return
    try:
        info = await hiddify_api.get_user_info(service['sub_uuid'])
        if not info or (isinstance(info, dict) and info.get('_not_found')):
            kb = [
                [InlineKeyboardButton("🗑️ حذف سرویس از ربات", callback_data=f"delete_service_{service['service_id']}")],
                [InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"refresh_{service['service_id']}")],
                [InlineKeyboardButton("⬅️ بازگشت به لیست سرویس‌ها", callback_data="back_to_services")]
            ]
            text = "❌ اطلاعات این سرویس در پنل یافت نشد. احتمالاً حذف شده است.\nمی‌خواهید این سرویس از ربات هم حذف شود؟"
            if original_message:
                try:
                    await original_message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb))
                except BadRequest:
                    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(kb))
            else:
                await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(kb))
            return

        caption = create_service_info_message(info, service_db_record=service)
        keyboard_rows = []
        if not minimal:
            keyboard_rows.append([
                InlineKeyboardButton("🔄 به‌روزرسانی اطلاعات", callback_data=f"refresh_{service['service_id']}"),
                InlineKeyboardButton("🔗 لینک‌های بیشتر", callback_data=f"more_links_{service['sub_uuid']}"),
            ])
            plan = db.get_plan(service.get('plan_id')) if service.get('plan_id') else None
            if plan:
                keyboard_rows.append([InlineKeyboardButton(f"⏳ تمدید سرویس ({plan['price']:.0f} تومان)", callback_data=f"renew_{service['service_id']}")])
            keyboard_rows.append([InlineKeyboardButton("🗑️ حذف سرویس", callback_data=f"delete_service_{service['service_id']}")])
            if is_from_menu:
                keyboard_rows.append([InlineKeyboardButton("⬅️ بازگشت به لیست سرویس‌ها", callback_data="back_to_services")])

        if original_message:
            try:
                await original_message.delete()
            except BadRequest:
                pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard_rows)
        )
    except Exception as e:
        logger.error("send_service_details error for service_id %s: %s", service_id, e, exc_info=True)
        text = "❌ خطا در دریافت اطلاعات سرویس. لطفاً بعداً دوباره تلاش کنید."
        if original_message:
            try:
                await original_message.edit_text(text)
            except BadRequest:
                await context.bot.send_message(chat_id=chat_id, text=text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)


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
    keyboard = [
        [InlineKeyboardButton("لینک V2ray (sub)", callback_data=f"getlink_sub_{user_uuid}"), InlineKeyboardButton("لینک هوشمند (Auto)", callback_data=f"getlink_auto_{user_uuid}")],
        [InlineKeyboardButton("لینک Base64 (sub64)", callback_data=f"getlink_sub64_{user_uuid}"), InlineKeyboardButton("لینک SingBox", callback_data=f"getlink_singbox_{user_uuid}")],
        [InlineKeyboardButton("لینک Xray", callback_data=f"getlink_xray_{user_uuid}"), InlineKeyboardButton("لینک Clash", callback_data=f"getlink_clash_{user_uuid}")],
        [InlineKeyboardButton("لینک Clash Meta", callback_data=f"getlink_clashmeta_{user_uuid}")],
        [InlineKeyboardButton("📄 نمایش کانفیگ‌های تکی", callback_data=f"getlink_full_{user_uuid}")],
        [InlineKeyboardButton("⬅️ بازگشت به جزئیات سرویس", callback_data=f"refresh_{service_id}")]
    ]
    text = "لطفاً نوع لینک اشتراک مورد نظر را انتخاب کنید:"
    try:
        if is_edit:
            if message.photo:
                try:
                    await message.delete()
                except BadRequest:
                    pass
                if context:
                    await context.bot.send_message(chat_id=message.chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except BadRequest as e:
        if "message is not modified" not in str(e):
            logger.error("show_link_options_menu error: %s", e)


async def get_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    parts = q.data.split('_')
    link_type, user_uuid = parts[1], parts[2]

    service = db.get_service_by_uuid(user_uuid)
    plan = db.get_plan(service.get('plan_id')) if service else None
    sub_domain = get_domain_for_plan(plan)

    from config import SUB_PATH, ADMIN_PATH
    sub_path = SUB_PATH or ADMIN_PATH
    base_link = f"https://{sub_domain}/{sub_path}/{user_uuid}"
    info = await hiddify_api.get_user_info(user_uuid)
    config_name = info.get('name', 'config') if info else 'config'

    if link_type == "full":
        try:
            await q.edit_message_text("در حال دریافت کانفیگ‌های تکی... ⏳")
        except BadRequest:
            pass
        full_config_link = f"{base_link}/all.txt"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(full_config_link)
                response.raise_for_status()
            configs_bytes = response.content
            try:
                await q.message.delete()
            except BadRequest:
                pass
            await context.bot.send_document(
                chat_id=q.from_user.id,
                document=InputFile(io.BytesIO(configs_bytes), filename=f"{config_name}_configs.txt"),
                caption="📄 کانفیگ‌های تکی شما به صورت فایل ارسال شد."
            )
        except Exception as e:
            logger.error("Failed to fetch/send full configs: %s", e, exc_info=True)
            try:
                await q.edit_message_text("❌ دریافت کانفیگ‌های تکی با خطا مواجه شد.")
            except BadRequest:
                await context.bot.send_message(chat_id=q.from_user.id, text="❌ دریافت کانفیگ‌های تکی با خطا مواجه شد.")
        return

    url_link_type = link_type.replace('clashmeta', 'clash-meta')
    final_link = f"{base_link}/{url_link_type}/?name={config_name.replace(' ', '_')}"

    img = qrcode.make(final_link)
    bio = io.BytesIO()
    bio.name = 'qrcode.png'
    img.save(bio, 'PNG')
    bio.seek(0)

    display_link_type = _link_label(link_type)
    caption = (
        f"نام کانفیگ: **{config_name}**\n"
        f"نوع لینک: **{display_link_type}**\n\n"
        "با اسکن QR یا استفاده از لینک زیر متصل شوید:\n\n"
        f"`{final_link}`"
    )

    try:
        await q.message.delete()
    except BadRequest:
        pass
    await context.bot.send_photo(
        chat_id=q.message.chat_id,
        photo=bio,
        caption=caption,
        parse_mode="Markdown"
    )


async def refresh_service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    service_id = int(q.data.split('_')[1])
    service = db.get_service(service_id)

    if not service or service['user_id'] != q.from_user.id:
        await q.answer("خطا: این سرویس متعلق به شما نیست.", show_alert=True)
        return

    try:
        await q.message.delete()
    except BadRequest:
        pass

    msg = await context.bot.send_message(chat_id=q.from_user.id, text="در حال به‌روزرسانی اطلاعات...")

    if q.from_user.id == ADMIN_ID:
        try:
            info = await hiddify_api.get_user_info(service['sub_uuid'])
            if info:
                debug_text = json.dumps(info, indent=2, ensure_ascii=False)
                await q.from_user.send_message(f"-- DEBUG INFO --\n<pre>{debug_text}</pre>", parse_mode="HTML")
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
        try:
            await q.edit_message_text("❌ ورودی نامعتبر.")
        except Exception:
            pass
        return

    service = db.get_service(service_id)
    if not service or service['user_id'] != q.from_user.id:
        try:
            await q.edit_message_text("❌ سرویس یافت نشد یا متعلق به شما نیست.")
        except Exception:
            pass
        return

    if data.startswith("delete_service_cancel_"):
        try:
            await send_service_details(context, q.from_user.id, service_id, original_message=q.message, is_from_menu=True)
        except Exception:
            pass
        return

    if not data.startswith("delete_service_confirm_"):
        confirm_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("❌ انصراف", callback_data=f"delete_service_cancel_{service_id}"),
                InlineKeyboardButton("✅ تایید حذف", callback_data=f"delete_service_confirm_{service_id}")
            ]
        ])
        await q.edit_message_text(
            "آیا از حذف این سرویس مطمئن هستید؟ این عمل سرویس را از پنل اصلی نیز حذف می‌کند و قابل بازگشت نیست.",
            reply_markup=confirm_kb
        )
        return

    # تایید حذف
    try:
        await q.edit_message_text("در حال حذف سرویس از پنل... ⏳")
    except BadRequest:
        pass

    try:
        success_on_panel = await hiddify_api.delete_user_from_panel(service['sub_uuid'])

        # اگر ناموفق، یک چک نهایی برای اطمینان از «عدم وجود» انجام بده
        if not success_on_panel:
            probe = await hiddify_api.get_user_info(service['sub_uuid'])
            if isinstance(probe, dict) and probe.get("_not_found"):
                success_on_panel = True

        if not success_on_panel:
            try:
                await q.edit_message_text("❌ حذف سرویس از پنل با خطا مواجه شد. لطفاً به پشتیبانی اطلاع دهید.")
            except BadRequest:
                pass
            return

        # حذف رکورد DB
        db.delete_service(service_id)

        try:
            await q.edit_message_text("✅ سرویس با موفقیت از پنل و ربات حذف شد.")
        except BadRequest:
            pass

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت به سرویس‌ها", callback_data="back_to_services")]
        ])
        try:
            await context.bot.send_message(chat_id=q.from_user.id, text="عملیات حذف کامل شد.", reply_markup=kb)
        except Exception:
            pass

    except Exception as e:
        logger.error("Delete service %s failed: %s", service_id, e, exc_info=True)
        try:
            await q.edit_message_text("❌ حذف سرویس با خطای ناشناخته مواجه شد.")
        except BadRequest:
            pass


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
        await context.bot.send_message(chat_id=user_id, text="❌ سرویس نامعتبر است.")
        return

    plan_id = service.get('plan_id')
    plan = db.get_plan(plan_id) if plan_id is not None else None
    if not plan:
        await context.bot.send_message(chat_id=user_id, text="❌ پلن تمدید برای این سرویس یافت نشد.")
        return

    user = db.get_or_create_user(user_id)
    if user['balance'] < plan['price']:
        await context.bot.send_message(chat_id=user_id, text=f"موجودی برای تمدید کافی نیست! (نیاز به {plan['price']:.0f} تومان)")
        return

    info = await hiddify_api.get_user_info(service['sub_uuid'])
    if not info:
        await context.bot.send_message(chat_id=user_id, text="❌ امکان دریافت اطلاعات سرویس از پنل وجود ندارد. لطفاً بعداً تلاش کنید.")
        return

    try:
        current_usage = float(info.get('current_usage_GB', 0))
        usage_limit = float(info.get('usage_limit_GB', 0))
    except Exception:
        current_usage, usage_limit = 0.0, 0.0
    remaining_gb = max(usage_limit - current_usage, 0.0)

    _, jalali_exp, _ = get_service_status(info)

    context.user_data['renewal_service_id'] = service_id
    context.user_data['renewal_plan_id'] = plan['plan_id']

    text = f"""
⚠️ هشدار تمدید

با تمدید، اعتبار زمانی و حجمی باقیمانده شما ریست می‌شود و دوره جدید از همین لحظه شروع خواهد شد.

وضعیت فعلی سرویس:
- تاریخ انقضا: {jalali_exp}
- حجم باقیمانده: {remaining_gb:.2f} گیگابایت

مشخصات تمدید:
- مدت: {plan['days']} روز
- حجم: {plan['gb']} گیگابایت
- قیمت: {plan['price']:,} تومان

آیا تایید می‌کنید؟
    """.strip()

    keyboard = [
        [InlineKeyboardButton("✅ بله، تمدید کن", callback_data="confirmrenew")],
        [InlineKeyboardButton("❌ خیر، لغو کن", callback_data="cancelrenew")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )


async def confirm_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await proceed_with_renewal(update, context, original_message=q.message)


async def proceed_with_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE, original_message=None):
    """
    انجام فرآیند تمدید سرویس با مدیریت خطای بهبود یافته
    """
    q = update.callback_query
    user_id = q.from_user.id if q else update.effective_user.id

    service_id = context.user_data.get('renewal_service_id')
    plan_id = context.user_data.get('renewal_plan_id')

    if not service_id or not plan_id:
        await _send_renewal_error(original_message, "❌ خطای داخلی: اطلاعات تمدید یافت نشد.")
        return

    if original_message:
        try:
            await original_message.edit_text("در حال ارسال درخواست تمدید به پنل... ⏳")
        except BadRequest:
            pass

    service, plan = await _validate_renewal_data(user_id, service_id, plan_id)
    if not service or not plan:
        await _send_renewal_error(original_message, "❌ اطلاعات سرویس یا پلن نامعتبر است.")
        return

    txn_id = db.initiate_renewal_transaction(user_id, service_id, plan_id)
    if not txn_id:
        await _send_renewal_error(original_message, "❌ مشکلی در شروع فرآیند تمدید پیش آمد (مثلاً عدم موجودی).")
        return

    try:
        new_info = await hiddify_api.renew_user_subscription(
            user_uuid=service['sub_uuid'],
            plan_days=plan['days'],
            plan_gb=plan['gb']
        )

        if not new_info:
            raise ValueError("پاسخ API نامعتبر است")

        db.finalize_renewal_transaction(txn_id, plan_id)

        if original_message:
            try:
                await original_message.edit_text("✅ سرویس با موفقیت تمدید شد! در حال نمایش اطلاعات جدید...")
            except BadRequest:
                pass

        await send_service_details(context, user_id, service_id, original_message=original_message, is_from_menu=True)

    except Exception as e:
        logger.error(f"Service renewal failed: {e}", exc_info=True)
        db.cancel_renewal_transaction(txn_id)
        await _send_renewal_error(original_message,
                                  "❌ خطا در تمدید سرویس. مشکلی در ارتباط با پنل وجود دارد. لطفاً به پشتیبانی اطلاع دهید.")

    context.user_data.clear()


async def _validate_renewal_data(user_id: int, service_id: int, plan_id: int):
    service = db.get_service(service_id)
    if not service or service['user_id'] != user_id:
        return None, None

    plan = db.get_plan(plan_id)
    if not plan:
        return service, None

    return service, plan


async def _send_renewal_error(message, error_text: str):
    if message:
        try:
            await message.edit_text(error_text)
        except Exception:
            try:
                await message.reply_text(error_text)
            except Exception:
                pass


async def cancel_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    try:
        await q.edit_message_text("عملیات تمدید لغو شد.")
    except BadRequest:
        pass