# -*- coding: utf-8 -*-

import io
import random
import qrcode
from telegram.ext import ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
import database as db
import hiddify_api
from config import SUB_DOMAINS, PANEL_DOMAIN, SUB_PATH, ADMIN_PATH
from bot.keyboards import get_main_menu_keyboard
from bot.utils import get_service_status
import logging

logger = logging.getLogger(__name__)

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

async def view_service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    service_id = int(q.data.split('_')[-1])
    await q.edit_message_text("در حال دریافت اطلاعات سرویس... ⏳")
    await send_service_details(context, q.from_user.id, service_id, original_message=q.message, is_from_menu=True)

async def send_service_details(context: ContextTypes.DEFAULT_TYPE, chat_id: int, service_id: int, original_message=None, is_from_menu: bool = False):
    service = db.get_service(service_id)
    if not service:
        text = "❌ سرویس مورد نظر یافت نشد."
        if original_message: await original_message.edit_text(text)
        else: await context.bot.send_message(chat_id=chat_id, text=text)
        return
    try:
        info = await hiddify_api.get_user_info(service['sub_uuid'])
        if not info:
            # Show delete option when panel returns nothing (likely 404)
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
        sub_path = SUB_PATH or ADMIN_PATH
        sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
        base_link = f"https://{sub_domain}/{sub_path}/{service['sub_uuid']}"
        config_name = info.get('name', 'config')
        final_link = f"{base_link}/?name={config_name.replace(' ', '_')}"
        img = qrcode.make(final_link)
        bio = io.BytesIO(); bio.name = 'qrcode.png'; img.save(bio, 'PNG'); bio.seek(0)

        caption = (
            f"🏷️ نام سرویس: **{service['name']}**\n\n"
            f"📊 حجم مصرفی: **{info.get('current_usage_GB', 0):.2f} / {info.get('usage_limit_GB', 0):.0f}** گیگ\n"
            f"🗓️ تاریخ انقضا: **{expiry_jalali}**\n"
            f"🚦 وضعیت: {status}\n\n"
            f"🔗 لینک اشتراک:\n`{final_link}`"
        )

        keyboard = [[InlineKeyboardButton("🔄 به‌روزرسانی اطلاعات", callback_data=f"refresh_{service['service_id']}")]]
        if service.get('plan_id', 0) > 0:
            from database import get_plan
            plan = get_plan(service['plan_id'])
            if plan:
                keyboard.append([InlineKeyboardButton(f"⏳ تمدید سرویس ({plan['price']:.0f} تومان)", callback_data=f"renew_{service['service_id']}")])
        if is_from_menu:
            keyboard.append([InlineKeyboardButton("⬅️ بازگشت به لیست سرویس‌ها", callback_data="back_to_services")])

        if original_message:
            try: await original_message.delete()
            except BadRequest: pass

        await context.bot.send_photo(
            chat_id=chat_id, photo=bio, caption=caption, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error("send_service_details error for service_id %s: %s", service_id, e, exc_info=True)
        text = "❌ خطا در دریافت اطلاعات سرویس. لطفاً بعداً دوباره تلاش کنید."
        if original_message:
            try: await original_message.edit_text(text)
            except BadRequest: pass
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)

async def refresh_service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    service_id = int(q.data.split('_')[1])
    service = db.get_service(service_id)
    if service and service['user_id'] == q.from_user.id:
        await q.message.delete()
        msg = await context.bot.send_message(chat_id=q.from_user.id, text="در حال به‌روزرسانی اطلاعات...")
        await send_service_details(context, q.from_user.id, service_id, original_message=msg, is_from_menu=True)
    else:
        await q.answer("خطا: این سرویس متعلق به شما نیست.", show_alert=True)

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
    try:
        service_id = int(q.data.split('_')[-1])
    except Exception:
        await q.edit_message_text("❌ ورودی نامعتبر.")
        return

    service = db.get_service(service_id)
    if not service or service['user_id'] != q.from_user.id:
        await q.edit_message_text("❌ سرویس یافت نشد یا متعلق به شما نیست.")
        return

    try:
        # Use internal connection to remove the stale record safely
        conn = db._connect_db()
        conn.execute("DELETE FROM active_services WHERE service_id = ? AND user_id = ?", (service_id, q.from_user.id))
        conn.commit()
        await q.edit_message_text("🗑️ سرویس از لیست شما حذف شد.")
        # Show updated list
        await list_my_services(update, context)
    except Exception as e:
        logger.error("Delete service %s failed: %s", service_id, e, exc_info=True)
        await q.edit_message_text("❌ حذف سرویس انجام نشد. لطفاً بعداً دوباره تلاش کنید.")