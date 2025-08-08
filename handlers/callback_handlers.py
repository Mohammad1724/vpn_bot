# -*- coding: utf-8 -*-
import logging
import io
import os
import random
import asyncio
import qrcode
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction
from telegram.error import Forbidden, BadRequest

import database as db
import hiddify_api
import keyboards
from utils import get_service_status_and_expiry
from handlers.decorators import check_channel_membership
from handlers.user_handlers import send_service_management_menu, start as start_command
from config import SUB_DOMAINS, PANEL_DOMAIN, SUB_PATH, ADMIN_PATH, ADMIN_ID

logger = logging.getLogger(__name__)

# --- User Callbacks ---

@check_channel_membership
async def show_service_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'show_service_management' callback to display service details."""
    service_id = int(update.callback_query.data.split('_')[-1])
    await send_service_management_menu(update, context, service_id)

@check_channel_membership
async def list_my_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'back_to_services' callback to show the list of services."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    await query.edit_message_text("در حال دریافت لیست سرویس‌های شما...")
    
    services = await db.get_user_services(user_id)
    if not services:
        await query.edit_message_text("شما در حال حاضر هیچ سرویس فعالی ندارید.")
        return

    keyboard = []
    for service in services:
        button_text = f"⚙️ {service['name']}" if service['name'] else f"⚙️ سرویس {service['service_id']}"
        callback_data = f"show_service_management_{service['service_id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("لطفا سرویسی که می‌خواهید مدیریتش کنید را انتخاب نمایید:", reply_markup=reply_markup)
    
@check_channel_membership
async def get_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, link_type, user_uuid = query.data.split('_')

    await query.edit_message_text("در حال ساخت لینک و QR Code... ⏳")

    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    base_link = f"https://{sub_domain}/{sub_path}/{user_uuid}"

    user_info = await hiddify_api.get_user_info(user_uuid)
    config_name = user_info.get('name', 'config') if user_info else 'config'

    suffix_map = {
        "auto": "/", "sub": "/sub/", "clash": "/clash/", "clashmeta": "/clashmeta/", "xray": "/xray/",
    }
    link_suffix = suffix_map.get(link_type, "/")
    final_link = f"{base_link}{link_suffix}"
    final_link_with_fragment = f"{final_link}?name={config_name.replace(' ', '_')}"

    # Generate QR code in a separate thread to avoid blocking
    def generate_qr():
        qr_image = qrcode.make(final_link_with_fragment)
        bio = io.BytesIO()
        bio.name = 'qrcode.png'
        qr_image.save(bio, 'PNG')
        bio.seek(0)
        return bio
        
    qr_bio = await asyncio.to_thread(generate_qr)

    caption = (f"نام کانفیگ: **{config_name}**\n\n"
               "می‌توانید با اسکن QR کد زیر یا با استفاده از لینک اشتراک، به سرویس متصل شوید.\n\n"
               f"لینک اشتراک شما:\n`{final_link_with_fragment}`")

    await query.message.delete()
    service = await db.get_service_by_uuid(user_uuid)
    keyboard = [[InlineKeyboardButton("⬅️ بازگشت به مدیریت سرویس", callback_data=f"show_service_management_{service['service_id']}")]]

    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=qr_bio,
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_channel_membership
async def show_single_configs_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = int(query.data.split('_')[-1])

    service = await db.get_service(service_id)
    if not service:
        await query.edit_message_text("❌ سرویس یافت نشد.")
        return

    await query.edit_message_text("در حال دریافت کانفیگ‌های تکی...")
    info = await hiddify_api.get_user_info(service['sub_uuid'])
    if not info:
        await query.edit_message_text("❌ خطا در دریافت اطلاعات از پنل.")
        return

    keyboard = keyboards.get_single_configs_keyboard(service_id, info)
    
    if len(keyboard.inline_keyboard) == 1: # Only back button exists
        await query.edit_message_text("هیچ کانفیگ تکی برای این سرویس یافت نشد.")
        return

    await query.edit_message_text("لطفاً نوع کانفیگ تکی مورد نظر را انتخاب کنید:", reply_markup=keyboard)

@check_channel_membership
async def get_single_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, config_type, service_id_str = query.data.split('_', 2)
    service_id = int(service_id_str)

    service = await db.get_service(service_id)
    if not service:
        await query.edit_message_text("❌ سرویس یافت نشد.")
        return

    await query.edit_message_text("در حال ساخت کانفیگ و QR کد... ⏳")
    info = await hiddify_api.get_user_info(service['sub_uuid'])

    config_key = f"{config_type}_link"
    single_config_link = info.get(config_key)

    if not single_config_link:
        await query.edit_message_text(f"❌ کانفیگ {config_type.upper()} یافت نشد.")
        return

    def generate_qr():
        qr_image = qrcode.make(single_config_link)
        bio = io.BytesIO()
        bio.name = 'qrcode.png'
        qr_image.save(bio, 'PNG')
        bio.seek(0)
        return bio
        
    qr_bio = await asyncio.to_thread(generate_qr)

    caption = (f"کانفیگ تکی **{config_type.upper()}** برای سرویس **{service['name']}**\n\n"
               "با اسکن QR کد یا کپی کردن متن زیر، کانفیگ را اضافه کنید:\n\n"
               f"`{single_config_link}`")

    await query.message.delete()
    keyboard = [[InlineKeyboardButton("⬅️ بازگشت به انتخاب کانفیگ", callback_data=f"single_configs_{service_id}")]]

    await context.bot.send_photo(
        chat_id=query.message.chat_id, photo=qr_bio, caption=caption,
        parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'check_join' callback after a user claims to have joined channels."""
    query = update.callback_query
    await query.answer("در حال بررسی عضویت شما...")
    # By deleting the message, we trigger the decorator again on the next action.
    await query.message.delete()
    # Also, clear the cache for this user
    for key in list(context.user_data.keys()):
        if key.startswith(f"join_check_{query.from_user.id}"):
            del context.user_data[key]
    await start_command(update, context)


# --- Renewal Callbacks ---
@check_channel_membership
async def renew_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    service = await db.get_service(service_id)
    if not service:
        await query.edit_message_text("❌ سرویس نامعتبر است.")
        return
        
    plan = await db.get_plan(service['plan_id'])
    if not plan:
        await query.edit_message_text("❌ پلن تمدید برای این سرویس یافت نشد.")
        return
        
    user = await db.get_user(user_id)
    if user['balance'] < plan['price']:
        await query.edit_message_text(f"موجودی برای تمدید کافی نیست! (نیاز به {plan['price']:.0f} تومان)")
        return

    await query.edit_message_text("در حال بررسی وضعیت سرویس... ⏳")
    hiddify_info = await hiddify_api.get_user_info(service['sub_uuid'])
    if not hiddify_info:
        await query.edit_message_text("❌ امکان دریافت اطلاعات سرویس از پنل وجود ندارد. لطفاً بعداً تلاش کنید.")
        return

    _, _, is_expired = await get_service_status_and_expiry(hiddify_info)
    
    context.user_data['renewal_service_id'] = service_id
    context.user_data['renewal_plan_id'] = plan['plan_id']

    if is_expired:
        await proceed_with_renewal(update, context)
    else:
        keyboard = [[
            InlineKeyboardButton("✅ بله، تمدید کن", callback_data=f"confirmrenew"),
            InlineKeyboardButton("❌ خیر، لغو کن", callback_data=f"cancelrenew")
        ]]
        await query.edit_message_text(
            "⚠️ **هشدار مهم** ⚠️\n\n"
            "سرویس شما هنوز اعتبار دارد. تمدید در حال حاضر باعث می‌شود اعتبار زمانی و حجمی باقیمانده شما **از بین برود** و دوره جدید از همین امروز شروع شود.\n\n"
            "آیا می‌خواهید ادامه دهید?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

async def confirm_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await proceed_with_renewal(update, context)

async def proceed_with_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    service_id = context.user_data.get('renewal_service_id')
    plan_id = context.user_data.get('renewal_plan_id')

    if not all([service_id, plan_id]):
        await query.edit_message_text("❌ خطای داخلی: اطلاعات تمدید یافت نشد.")
        return

    await query.edit_message_text("در حال ارسال درخواست تمدید به پنل... ⏳")

    transaction_id = await db.initiate_renewal_transaction(user_id, service_id, plan_id)
    if not transaction_id:
        await query.edit_message_text("❌ مشکلی در شروع فرآیند تمدید پیش آمد (مثلا عدم موجودی).")
        return

    service = await db.get_service(service_id)
    plan = await db.get_plan(plan_id)

    new_hiddify_info = await hiddify_api.renew_user_subscription(service['sub_uuid'], plan['days'], plan['gb'])

    if new_hiddify_info:
        await db.finalize_renewal_transaction(transaction_id, plan['plan_id'])
        await query.edit_message_text("✅ سرویس با موفقیت تمدید شد! در حال نمایش منوی مدیریت...")
        await asyncio.sleep(1)
        await send_service_management_menu(update, context, service_id)
    else:
        await db.cancel_renewal_transaction(transaction_id)
        await query.edit_message_text("❌ خطا در تمدید سرویس. هزینه به حساب شما بازگشت. لطفاً به پشتیبانی اطلاع دهید.")

    context.user_data.clear()

async def cancel_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("عملیات تمدید لغو شد.")
    context.user_data.clear()


# --- Admin Callbacks ---
async def admin_confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("در حال تایید شارژ...")
    
    try:
        parts = query.data.split('_')
        target_user_id = int(parts[-2])
        amount = int(parts[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing admin_confirm_charge_callback data: {query.data} | Error: {e}")
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n---\n❌ خطا در پردازش اطلاعات دکمه.")
        return

    await db.update_balance(target_user_id, amount)
    
    admin_feedback = f"{query.message.caption}\n\n---\n✅ با موفقیت مبلغ {amount:,.0f} تومان به حساب کاربر `{target_user_id}` اضافه شد."

    try: 
        await context.bot.send_message(
            chat_id=target_user_id, 
            text=f"حساب شما با موفقیت به مبلغ **{amount:,.0f} تومان** شارژ شد!", 
            parse_mode=ParseMode.MARKDOWN
        )
    except (Forbidden, BadRequest):
        admin_feedback += "\n\n⚠️ **اخطار:** کاربر ربات را بلاک کرده و پیام تایید را دریافت نکرد."

    await query.edit_message_caption(caption=admin_feedback, reply_markup=None, parse_mode=ParseMode.MARKDOWN)

async def admin_reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("در حال رد درخواست...")
    
    target_user_id = int(query.data.split('_')[-1])
    admin_feedback = f"{query.message.caption}\n\n---\n❌ درخواست شارژ کاربر `{target_user_id}` رد شد."

    try: 
        await context.bot.send_message(chat_id=target_user_id, text="متاسفانه درخواست شارژ حساب شما توسط ادمین رد شد.")
    except (Forbidden, BadRequest): 
        admin_feedback += "\n\n⚠️ **اخطار:** کاربر ربات را بلاک کرده است."

    await query.edit_message_caption(caption=admin_feedback, reply_markup=None, parse_mode=ParseMode.MARKDOWN)

async def admin_delete_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    plan_id = int(query.data.split('_')[-1])
    await db.delete_plan(plan_id)
    await query.answer("پلن با موفقیت حذف شد.", show_alert=True)
    await query.message.delete()
    
async def admin_toggle_plan_visibility_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    plan_id = int(query.data.split('_')[-1])
    await db.toggle_plan_visibility(plan_id)
    await query.answer("وضعیت نمایش پلن تغییر کرد.", show_alert=True)
    # Refresh the list for the admin
    from handlers.admin_handlers import list_plans_admin
    await query.message.delete()
    await list_plans_admin(update, context)

async def admin_confirm_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    restore_path = context.user_data.get('restore_path')
    if not restore_path or not os.path.exists(restore_path): 
        await query.answer("خطا: فایل پشتیبان یافت نشد.", show_alert=True)
        return
        
    await query.edit_message_text("در حال بازیابی دیتابیس... لطفاً صبور باشید.")
    
    try:
        await db.close_db()
        # Run blocking I/O in a thread
        def _restore_db():
            # Create a backup of the current DB before overwriting
            current_db_backup_path = f"{db.DB_NAME}.{datetime.now().timestamp()}.bak"
            shutil.move(db.DB_NAME, current_db_backup_path)
            shutil.move(restore_path, db.DB_NAME)

        await asyncio.to_thread(_restore_db)

        # Re-initialize the application's connection pool
        await db.init_db() 
        
        await query.edit_message_text(
            "✅ دیتابیس با موفقیت بازیابی شد.\n\n"
            "**مهم:** برای اعمال کامل تغییرات، لطفاً ربات را با دستور /start (در صورت نیاز) یا ری‌استارت کامل، مجدداً راه‌اندازی کنید.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error during DB restore: {e}", exc_info=True)
        await query.edit_message_text(f"❌ خطا در هنگام جایگزینی فایل دیتابیس: {e}")
        
    context.user_data.clear()

async def admin_cancel_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    restore_path = context.user_data.get('restore_path')
    if restore_path and os.path.exists(restore_path):
        await asyncio.to_thread(os.remove, restore_path)
    await query.answer("عملیات لغو شد.")
    await query.edit_message_text("عملیات بازیابی لغو شد.")
    context.user_data.clear()

async def admin_link_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    recommended_type = await db.get_setting('recommended_link_type') or 'auto'
    def get_check(link_type): return "✅ " if recommended_type == link_type else ""

    keyboard = [
        [InlineKeyboardButton(f"{get_check('auto')}لینک هوشمند (Auto)", callback_data="set_rec_link_auto")],
        [InlineKeyboardButton(f"{get_check('sub')}لینک استاندارد (Sub)", callback_data="set_rec_link_sub")],
        [InlineKeyboardButton(f"{get_check('clash')}لینک Clash", callback_data="set_rec_link_clash")],
        [InlineKeyboardButton(f"{get_check('clashmeta')}لینک Clash Meta", callback_data="set_rec_link_clashmeta")],
        [InlineKeyboardButton(f"{get_check('xray')}لینک Xray", callback_data="set_rec_link_xray")],
        [InlineKeyboardButton("⬅️ بازگشت به تنظیمات", callback_data="back_to_settings")]
    ]

    await query.edit_message_text(
        "لطفاً نوع لینکی که می‌خواهید به کاربران پیشنهاد شود را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def set_recommended_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    link_type = query.data.split('_')[-1]

    await db.set_setting('recommended_link_type', link_type)
    await query.answer(f"لینک {link_type.capitalize()} به عنوان پیشنهاد انتخاب شد.", show_alert=True)
    await admin_link_settings_menu(update, context) # Refresh the menu

async def back_to_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.admin_handlers import settings_menu
    await query.answer()
    await settings_menu(update, context)
