# -*- coding: utf-8 -*-

import io
import random
import qrcode
import logging
import httpx
from telegram.ext import ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.error import BadRequest
import database as db
import hiddify_api
from config import SUB_DOMAINS, PANEL_DOMAIN, SUB_PATH, ADMIN_PATH
from bot.keyboards import get_main_menu_keyboard
from bot.utils import get_service_status

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
        if not info or (isinstance(info, dict) and info.get('_not_found')):
            kb = [
                [InlineKeyboardButton("🗑️ حذف سرویس از ربات", callback_data=f"delete_service_{service['service_id']}")],
                [InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"refresh_{service['service_id']}")],
                [InlineKeyboardButton("⬅️ بازگشت به لیست سرویس‌ها", callback_data="back_to_services")]
            ]
            text = "❌ اطلاعات این سرویس در پنل یافت نشد. احتمالاً حذف شده است.\nمی‌خواهید این سرویس از ربات هم حذف شود؟"
            if original_message:
                await original_message.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            else:
                await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(kb))
            return

        status, expiry_jalali, _ = get_service_status(info)
        default_link_type = db.get_setting('default_sub_link_type') or 'sub'
        
        sub_path = SUB_PATH or ADMIN_PATH
        sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
        base_link = f"https://{sub_domain}/{sub_path}/{service['sub_uuid']}"
        config_name = info.get('name', 'config')
        
        final_link = f"{base_link}/{default_link_type}/?name={config_name.replace(' ', '_')}"
        img = qrcode.make(final_link)
        bio = io.BytesIO(); bio.name = 'qrcode.png'; img.save(bio, 'PNG'); bio.seek(0)

        caption = (
            f"🏷️ نام سرویس: **{service['name']}**\n\n"
            f"📊 حجم مصرفی: **{info.get('current_usage_GB', 0):.2f} / {info.get('usage_limit_GB', 0):.0f}** گیگ\n"
            f"🗓️ تاریخ انقضا: **{expiry_jalali}**\n"
            f"🚦 وضعیت: {status}\n\n"
            f"🔗 لینک اشتراک (پیش‌فرض):\n`{final_link}`"
        )

        keyboard = [[InlineKeyboardButton("🔄 به‌روزرسانی اطلاعات", callback_data=f"refresh_{service['service_id']}")]]
        if service.get('plan_id', 0) > 0:
            plan = db.get_plan(service['plan_id'])
            if plan:
                keyboard.append([InlineKeyboardButton(f"⏳ تمدید سرویس ({plan['price']:.0f} تومان)", callback_data=f"renew_{service['service_id']}")])
        
        keyboard.append([InlineKeyboardButton("🔗 دریافت لینک‌های بیشتر", callback_data=f"more_links_{service['sub_uuid']}")])
        
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

async def more_links_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uuid = q.data.split('_')[-1]
    
    service = db.get_service_by_uuid(uuid)
    if not service:
        await q.edit_message_text("سرویس یافت نشد.")
        return
        
    await show_link_options_menu(q.message, uuid, service['service_id'], is_edit=True)

async def show_link_options_menu(message: Message, user_uuid: str, service_id: int, is_edit: bool = True):
    keyboard = [
        [InlineKeyboardButton("لینک V2ray (sub)", callback_data=f"getlink_sub_{user_uuid}"),
         InlineKeyboardButton("لینک هوشمند (Auto)", callback_data=f"getlink_auto_{user_uuid}")],
        [InlineKeyboardButton("لینک Base64 (sub64)", callback_data=f"getlink_sub64_{user_uuid}"),
         InlineKeyboardButton("لینک SingBox", callback_data=f"getlink_singbox_{user_uuid}")],
        [InlineKeyboardButton("لینک Xray", callback_data=f"getlink_xray_{user_uuid}"),
         InlineKeyboardButton("لینک Clash", callback_data=f"getlink_clash_{user_uuid}")],
        [InlineKeyboardButton("لینک Clash Meta", callback_data=f"getlink_clashmeta_{user_uuid}")],
        [InlineKeyboardButton("📄 نمایش کانفیگ‌های تکی", callback_data=f"getlink_full_{user_uuid}")],
        [InlineKeyboardButton("⬅️ بازگشت به جزئیات سرویس", callback_data=f"refresh_{service_id}")]
    ]
    text = "لطفاً نوع لینک اشتراک مورد نظر را انتخاب کنید:"
    try:
        if is_edit:
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
    
    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    base_link = f"https://{sub_domain}/{sub_path}/{user_uuid}"
    
    info = await hiddify_api.get_user_info(user_uuid)
    config_name = info.get('name', 'config') if info else 'config'

    if link_type == "full":
        await q.edit_message_text("در حال دریافت کانفیگ‌های تکی... ⏳")
        full_config_link = f"{base_link}/all.txt"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(full_config_link)
                response.raise_for_status()
            configs = response.text
            text_to_send = f"📄 **کانفیگ‌های تکی برای سرویس شما:**\n\n`{configs}`"
            await q.edit_message_text(text_to_send, parse_mode="Markdown")
        except Exception as e:
            logger.error("Failed to fetch full configs: %s", e)
            await q.edit_message_text("❌ دریافت کانفیگ‌های تکی با خطا مواجه شد.")
        return

    # Handle clashmeta correctly for URL
    url_link_type = link_type.replace('clashmeta', 'clash-meta')
    final_link = f"{base_link}/{url_link_type}/?name={config_name.replace(' ', '_')}"
    
    img = qrcode.make(final_link)
    bio = io.BytesIO(); bio.name = 'qrcode.png'; img.save(bio, 'PNG'); bio.seek(0)
    
    # Beautify link type name for the caption
    display_link_type = link_type.replace('sub', 'V2ray').replace('meta', ' Meta').title()
    caption = (
        f"نام کانفیگ: **{config_name}**\n"
        f"نوع لینک: **{display_link_type}**\n\n"
        "با اسکن QR یا استفاده از لینک زیر متصل شوید:\n\n"
        f"`{final_link}`"
    )
    
    await q.message.delete()
    await context.bot.send_photo(
        chat_id=q.message.chat_id,
        photo=bio,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(q.from_user.id)
    )

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
        db.delete_service(service_id)
        await q.edit_message_text("🗑️ سرویس از لیست شما حذف شد.")
        await list_my_services(update, context)
    except Exception as e:
        logger.error("Delete service %s failed: %s", service_id, e, exc_info=True)
        await q.edit_message_text("❌ حذف سرویس انجام نشد. لطفاً بعداً دوباره تلاش کنید.")