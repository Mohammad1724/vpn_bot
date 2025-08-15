# -*- coding: utf-8 -*-

import io
import json
import random
import qrcode
import logging
import httpx
from telegram.ext import ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, InputFile
from telegram.error import BadRequest
import database as db
import hiddify_api
from config import MERGER_BASE_URL, ADMIN_ID
from bot.keyboards import get_main_menu_keyboard
from bot.utils import get_service_status

logger = logging.getLogger(__name__)

# ===== Helpers =====
def _normalize_link_type(t: str) -> str:
    t = (t or "sub").strip().lower().replace("clash-meta", "clashmeta")
    return t

def _link_label(link_type: str) -> str:
    lt = _normalize_link_type(link_type)
    mapping = {
        "sub": "V2Ray (sub)",
        "auto": "هوشمند (Auto)",
        "sub64": "Base64 (sub64)",
        "singbox": "SingBox",
        "xray": "Xray",
        "clash": "Clash",
        "clashmeta": "Clash Meta",
    }
    return mapping.get(lt, "V2Ray (sub)")

# ===== لیست سرویس‌ها =====
async def list_my_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    services = db.get_user_services(user_id)
    if not services:
        await context.bot.send_message(chat_id=user_id, text="شما در حال حاضر هیچ سرویس فعالی ندارید.")
        return
    keyboard = []
    for service in services:
        title = service['name'] or "سرویس بدون نام"
        keyboard.append([InlineKeyboardButton(f"⚙️ {title}", callback_data=f"view_service_{service['service_id']}")])
    await context.bot.send_message(
        chat_id=user_id,
        text="لطفاً سرویسی که می‌خواهید مدیریتش کنید را انتخاب نمایید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===== نمایش جزئیات سرویس =====
async def view_service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    service_id = int(q.data.split('_')[-1])
    if q.message:
        await q.message.delete()
    msg = await context.bot.send_message(chat_id=q.from_user.id, text="در حال دریافت اطلاعات سرویس... ⏳")
    await send_service_details(context, q.from_user.id, service_id, original_message=msg, is_from_menu=True)

async def send_service_details(context: ContextTypes.DEFAULT_TYPE, chat_id: int, service_id: int, original_message=None, is_from_menu: bool = False, minimal: bool = False):
    service = db.get_service(service_id)
    if not service:
        text = "❌ سرویس مورد نظر یافت نشد."
        if original_message: await original_message.edit_text(text)
        else: await context.bot.send_message(chat_id=chat_id, text=text)
        return
    try:
        info = await hiddify_api.get_user_info_from_panel(1, service['sub_uuid'])
        if not info or (isinstance(info, dict) and info.get('_not_found')):
            kb = [
                [InlineKeyboardButton("🗑️ حذف سرویس از ربات", callback_data=f"delete_service_{service['service_id']}")],
                [InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"refresh_{service['service_id']}")],
                [InlineKeyboardButton("⬅️ بازگشت به لیست سرویس‌ها", callback_data="back_to_services")]
            ]
            text = "❌ اطلاعات این سرویس در پنل یافت نشد. احتمالاً حذف شده است.\nمی‌خواهید این سرویس از ربات هم حذف شود؟"
            if original_message:
                await original_message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb))
            else:
                await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(kb))
            return

        status, expiry_jalali, _ = get_service_status(info)

        caption = (
            f"🏷️ نام سرویس: **{service['name']}**\n\n"
            f"📊 حجم مصرفی: **{info.get('current_usage_GB', 0):.2f} / {info.get('usage_limit_GB', 0):.0f}** گیگ\n"
            f"🗓️ تاریخ انقضا: **{expiry_jalali}**\n"
            f"🚦 وضعیت: {status}\n\n"
            f"برای دریافت لینک‌ها از دکمه‌های زیر استفاده کنید:"
        )

        keyboard_rows = []
        keyboard_rows.append([
            InlineKeyboardButton("⚡ دریافت لینک ادغام‌شده", callback_data=f"getlink_merged_{service['sub_uuid']}")
        ])
        
        if not minimal:
            keyboard_rows.append([InlineKeyboardButton("🔄 به‌روزرسانی اطلاعات", callback_data=f"refresh_{service['service_id']}")])
            plan_id = service.get('plan_id')
            plan = db.get_plan(plan_id) if plan_id is not None else None
            if plan:
                keyboard_rows.append([InlineKeyboardButton(f"⏳ تمدید سرویس ({plan['price']:.0f} تومان)", callback_data=f"renew_{service['service_id']}")])
            keyboard_rows.append([InlineKeyboardButton("🗑️ حذف سرویس", callback_data=f"delete_service_{service['service_id']}")])
            if is_from_menu:
                keyboard_rows.append([InlineKeyboardButton("⬅️ بازگشت به لیست سرویس‌ها", callback_data="back_to_services")])

        if original_message:
            try: await original_message.delete()
            except BadRequest: pass

        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard_rows)
        )
    except Exception as e:
        logger.error("send_service_details error for service_id %s: %s", service_id, e, exc_info=True)
        text = "❌ خطا در دریافت اطلاعات سرویس. لطفاً بعداً دوباره تلاش کنید."
        if original_message:
            try: await original_message.edit_text(text)
            except BadRequest: pass
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)

# ===== تولید لینک‌ها و QR =====
async def get_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    parts = q.data.split('_')
    link_type, user_uuid = parts[1], parts[2]

    if link_type == "merged":
        final_link = f"{MERGER_BASE_URL.rstrip('/')}/sub/{user_uuid}"
    else:
        await q.message.edit_text("این نوع لینک دیگر پشتیبانی نمی‌شود. لطفاً از لینک ادغام‌شده استفاده کنید.")
        return

    img = qrcode.make(final_link)
    bio = io.BytesIO(); bio.name = 'qrcode.png'; img.save(bio, 'PNG'); bio.seek(0)

    caption = (
        f"🔗 لینک اشتراک ادغام‌شده شما:\n\n"
        "با اسکن QR یا استفاده از لینک زیر، کانفیگ‌های هر دو سرور را دریافت کنید:\n\n"
        f"`{final_link}`"
    )
    
    try:
        await q.message.delete()
    except Exception:
        pass
        
    await context.bot.send_photo(
        chat_id=q.message.chat_id,
        photo=bio,
        caption=caption,
        parse_mode="Markdown"
    )

# ===== به‌روزرسانی جزئیات (با قابلیت دیباگ برای ادمین) =====
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
    
    # اگر کاربر ادمین است، خروجی کامل API را برای دیباگ بفرست
    if q.from_user.id == ADMIN_ID:
        try:
            info = await hiddify_api.get_user_info_from_panel(1, service['sub_uuid'])
            if info:
                debug_text = json.dumps(info, indent=2, ensure_ascii=False)
                await q.from_user.send_message(f"-- DEBUG INFO (Panel 1) --\n<pre>{debug_text}</pre>", parse_mode="HTML")
        except Exception as e:
            await q.from_user.send_message(f"Debug error: {e}")

    await send_service_details(context, q.from_user.id, service_id, original_message=msg, is_from_menu=True)

# ===== بازگشت به لیست =====
async def back_to_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        await q.message.delete()
    except BadRequest:
        pass
    await list_my_services(update, context)

# ===== حذف سرویس (با تایید دو مرحله‌ای) =====
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

    if data.startswith("delete_service_confirm_"):
        try:
            await q.edit_message_text("در حال حذف سرویس از پنل‌ها... ⏳")
            
            p1_ok = await hiddify_api.delete_user_from_panel(1, service['sub_uuid'])
            p2_ok = await hiddify_api.delete_user_from_panel(2, service['sub_uuid'])
            
            if not (p1_ok and p2_ok):
                await q.edit_message_text("❌ حذف سرویس از یک یا هر دو پنل با خطا مواجه شد. لطفاً به پشتیبانی اطلاع دهید.")
                return

            db.delete_service(service_id)
            await q.edit_message_text("✅ سرویس با موفقیت از هر دو پنل و ربات حذف شد.")
        except Exception as e:
            logger.error("Delete service %s failed: %s", service_id, e, exc_info=True)
            await q.edit_message_text("❌ حذف سرویس با خطای ناشناخته مواجه شد.")
            return

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به سرویس‌ها", callback_data="back_to_services")]])
        await context.bot.send_message(chat_id=q.from_user.id, text="عملیات حذف کامل شد.", reply_markup=kb)
        return

    if data.startswith("delete_service_cancel_"):
        try:
            await send_service_details(context, q.from_user.id, service_id, original_message=q.message, is_from_menu=True)
        except Exception:
            pass
        return

    confirm_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❌ انصراف", callback_data=f"delete_service_cancel_{service_id}"),
            InlineKeyboardButton("✅ تایید حذف", callback_data=f"delete_service_confirm_{service_id}")
        ]
    ])
    await q.edit_message_text("آیا از حذف این سرویس مطمئن هستید؟ این عمل سرویس را از هر دو پنل حذف می‌کند و قابل بازگشت نیست.", reply_markup=confirm_kb)

# ===== تمدید (شروع → تایید/لغو) =====
async def renew_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.delete()
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

    msg = await context.bot.send_message(chat_id=user_id, text="در حال بررسی وضعیت سرویس... ⏳")
    info = await hiddify_api.get_user_info_from_panel(1, service['sub_uuid'])
    if not info:
        await msg.edit_text("❌ امکان دریافت اطلاعات سرویس از پنل وجود ندارد. لطفاً بعداً تلاش کنید.")
        return

    _, _, is_expired = get_service_status(info)
    context.user_data['renewal_service_id'] = service_id
    context.user_data['renewal_plan_id'] = plan['plan_id']

    if is_expired:
        await proceed_with_renewal(update, context, original_message=msg)
    else:
        kb = [
            [InlineKeyboardButton("✅ بله، تمدید کن", callback_data="confirmrenew")],
            [InlineKeyboardButton("❌ خیر، لغو کن", callback_data="cancelrenew")]
        ]
        await msg.edit_text(
            "⚠️ هشدار مهم\n\nسرویس شما هنوز اعتبار دارد. تمدید در حال حاضر باعث می‌شود اعتبار زمانی و حجمی باقیمانده شما از بین برود و دوره جدید از امروز شروع شود.\n\nآیا ادامه می‌دهید؟",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )

async def confirm_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await proceed_with_renewal(update, context, original_message=q.message)

async def proceed_with_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE, original_message=None):
    q = update.callback_query
    user_id = q.from_user.id if q else update.effective_user.id
    service_id = context.user_data.get('renewal_service_id')
    plan_id = context.user_data.get('renewal_plan_id')
    if not service_id or not plan_id:
        if original_message: await original_message.edit_text("❌ خطای داخلی: اطلاعات تمدید یافت نشد.")
        return

    if original_message:
        await original_message.edit_text("در حال ارسال درخواست تمدید به پنل‌ها... ⏳")

    txn_id = db.initiate_renewal_transaction(user_id, service_id, plan_id)
    if not txn_id:
        if original_message:
            await original_message.edit_text("❌ مشکلی در شروع فرآیند تمدید پیش آمد (مثلاً عدم موجودی).")
        return

    service = db.get_service(service_id)
    plan = db.get_plan(plan_id)
    
    p1_res = await hiddify_api.renew_user_on_panel(1, service['sub_uuid'], plan['days'], plan['gb'])
    p2_res = await hiddify_api.renew_user_on_panel(2, service['sub_uuid'], plan['days'], plan['gb'])

    if p1_res and p2_res:
        db.finalize_renewal_transaction(txn_id, plan_id)
        if original_message:
            await original_message.edit_text("✅ سرویس با موفقیت تمدید شد! در حال نمایش اطلاعات جدید...")
        await send_service_details(context, user_id, service_id, original_message=original_message, is_from_menu=True)
    else:
        db.cancel_renewal_transaction(txn_id)
        if original_message:
            await original_message.edit_text("❌ خطا در تمدید سرویس. مشکلی در ارتباط با یک یا هر دو پنل وجود دارد. لطفاً به پشتیبانی اطلاع دهید.")

    context.user_data.clear()

async def cancel_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("عملیات تمدید لغو شد.")