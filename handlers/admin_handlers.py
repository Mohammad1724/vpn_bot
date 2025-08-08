# -*- coding: utf-8 -*-
import logging
import os
import shutil
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import Forbidden, BadRequest

import database as db
import keyboards
from constants import *
from utils import is_valid_sqlite
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# --- Generic Admin Handlers ---
async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👑 به پنل ادمین خوش آمدید.", reply_markup=keyboards.get_admin_menu_keyboard())
    return ADMIN_MENU

async def exit_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("شما از پنل ادمین خارج شدید.", reply_markup=await keyboards.get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END

async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("به منوی اصلی ادمین بازگشتید.", reply_markup=keyboards.get_admin_menu_keyboard())
    return ADMIN_MENU

async def admin_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=keyboards.get_admin_menu_keyboard())
    return ConversationHandler.END


# --- Plan Management ---
async def plan_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بخش مدیریت پلن‌ها", reply_markup=keyboards.get_plan_management_keyboard())
    return PLAN_MENU

async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = await db.list_plans()
    if not plans: 
        await update.message.reply_text("هیچ پلنی تعریف نشده است.")
        return PLAN_MENU
    
    await update.message.reply_text("لیست پلن‌های تعریف شده:")
    for plan in plans:
        visibility_icon = "👁️" if plan['is_visible'] else "🙈"
        text = (f"**{plan['name']}** (ID: {plan['plan_id']})\n"
                f"▫️ قیمت: {plan['price']:.0f} تومان\n"
                f"▫️ مدت: {plan['days']} روز\n"
                f"▫️ حجم: {plan['gb']} گیگ\n"
                f"▫️ وضعیت: {'نمایش' if plan['is_visible'] else 'مخفی'}")
        keyboard = [[
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"admin_edit_plan_{plan['plan_id']}"),
            InlineKeyboardButton(f"{visibility_icon} تغییر وضعیت", callback_data=f"admin_toggle_plan_{plan['plan_id']}"),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"admin_delete_plan_{plan['plan_id']}")
        ]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return PLAN_MENU

# Plan Add Flow
async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا نام پلن را وارد کنید:", reply_markup=keyboards.get_cancel_keyboard())
    return PLAN_NAME

async def plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['plan_name'] = update.message.text
    await update.message.reply_text("نام ثبت شد. قیمت را به تومان وارد کنید:")
    return PLAN_PRICE

async def plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_price'] = float(update.message.text)
        await update.message.reply_text("قیمت ثبت شد. تعداد روزهای اعتبار را وارد کنید:")
        return PLAN_DAYS
    except ValueError: 
        await update.message.reply_text("لطفا قیمت را به صورت عدد وارد کنید.")
        return PLAN_PRICE

async def plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_days'] = int(update.message.text)
        await update.message.reply_text("تعداد روز ثبت شد. حجم سرویس به گیگابایت را وارد کنید:")
        return PLAN_GB
    except ValueError: 
        await update.message.reply_text("لطفا تعداد روز را به صورت عدد وارد کنید.")
        return PLAN_DAYS

async def plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_gb'] = int(update.message.text)
        await db.add_plan(
            context.user_data['plan_name'],
            context.user_data['plan_price'],
            context.user_data['plan_days'],
            context.user_data['plan_gb']
        )
        await update.message.reply_text("✅ پلن جدید با موفقیت اضافه شد!", reply_markup=keyboards.get_admin_menu_keyboard())
        context.user_data.clear()
        return ADMIN_MENU
    except ValueError: 
        await update.message.reply_text("لطفا حجم را به صورت عدد وارد کنید.")
        return PLAN_GB

# Plan Edit Flow (Separate Conversation)
async def edit_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split('_')[-1])
    plan = await db.get_plan(plan_id)
    if not plan: 
        await query.edit_message_text("خطا: پلن یافت نشد.")
        return ConversationHandler.END
    
    context.user_data['edit_plan_id'] = plan_id
    context.user_data['edit_plan_data'] = {}
    
    await query.message.reply_text(
        f"در حال ویرایش پلن: **{plan['name']}**\n\n"
        f"لطفا نام جدید را وارد کنید. برای رد شدن، {CMD_SKIP} را بزنید.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboards.get_skip_cancel_keyboard()
    )
    return EDIT_PLAN_NAME

async def edit_plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['edit_plan_data']['name'] = update.message.text
    await update.message.reply_text(f"نام جدید ثبت شد. لطفاً قیمت جدید را به تومان وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_PRICE

async def skip_edit_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر نام صرف نظر شد. لطفاً قیمت جدید را به تومان وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_PRICE

# ... (Implement received/skip for price, days, gb similar to name)
async def edit_plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['price'] = float(update.message.text)
        await update.message.reply_text(f"قیمت جدید ثبت شد. لطفاً تعداد روزهای جدید را وارد کنید (یا {CMD_SKIP}).")
        return EDIT_PLAN_DAYS
    except ValueError:
        await update.message.reply_text("لطفا قیمت را به صورت عدد وارد کنید.")
        return EDIT_PLAN_PRICE

async def skip_edit_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر قیمت صرف نظر شد. لطفاً تعداد روزهای جدید را وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_DAYS

async def edit_plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['days'] = int(update.message.text)
        await update.message.reply_text(f"تعداد روز جدید ثبت شد. لطفاً حجم جدید به گیگابایت را وارد کنید (یا {CMD_SKIP}).")
        return EDIT_PLAN_GB
    except ValueError:
        await update.message.reply_text("لطفا تعداد روز را به صورت عدد وارد کنید.")
        return EDIT_PLAN_DAYS

async def skip_edit_plan_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر تعداد روز صرف نظر شد. لطفاً حجم جدید به گیگابایت را وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_GB

async def edit_plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['gb'] = int(update.message.text)
        await finish_plan_edit(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("لطفا حجم را به صورت عدد وارد کنید.")
        return EDIT_PLAN_GB

async def skip_edit_plan_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("از تغییر حجم صرف نظر شد.")
    await finish_plan_edit(update, context)
    return ConversationHandler.END

async def finish_plan_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_id = context.user_data.get('edit_plan_id')
    new_data = context.user_data.get('edit_plan_data')
    
    if not new_data: 
        await update.message.reply_text("هیچ تغییری اعمال نشد.", reply_markup=keyboards.get_admin_menu_keyboard())
    else:
        await db.update_plan(plan_id, new_data)
        await update.message.reply_text("✅ پلن با موفقیت به‌روزرسانی شد!", reply_markup=keyboards.get_admin_menu_keyboard())
        
    context.user_data.clear()

async def admin_conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generic cancel for admin conversations."""
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=keyboards.get_admin_menu_keyboard())
    return ConversationHandler.END


# --- Reports & Stats ---
async def reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بخش گزارش‌ها و آمار", reply_markup=keyboards.get_reports_menu_keyboard())
    return REPORTS_MENU

async def show_stats_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await db.get_stats()
    text = (f"📊 **آمار کلی ربات**\n\n"
            f"👥 تعداد کل کاربران: {stats.get('total_users', 0)}\n"
            f"✅ تعداد سرویس‌های فعال: {stats.get('active_services', 0)}\n"
            f"💰 مجموع فروش کل: {stats.get('total_revenue', 0):,.0f} تومان\n"
            f"🚫 تعداد کاربران مسدود: {stats.get('banned_users', 0)}")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return REPORTS_MENU

async def show_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sales = await db.get_sales_report(days=1)
    total_revenue = sum(s['price'] for s in sales)
    await update.message.reply_text(f"📈 **گزارش فروش امروز**\n\nتعداد فروش: {len(sales)}\nمجموع درآمد: {total_revenue:,.0f} تومان")
    return REPORTS_MENU

async def show_weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sales = await db.get_sales_report(days=7)
    total_revenue = sum(s['price'] for s in sales)
    await update.message.reply_text(f"📅 **گزارش فروش ۷ روز اخیر**\n\nتعداد فروش: {len(sales)}\nمجموع درآمد: {total_revenue:,.0f} تومان")
    return REPORTS_MENU

async def show_popular_plans_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = await db.get_popular_plans(limit=5)
    if not plans:
        await update.message.reply_text("هنوز هیچ پلنی فروخته نشده است.")
        return REPORTS_MENU
    
    text = "🏆 **محبوب‌ترین پلن‌ها**\n\n" + "\n".join([f"{i}. **{plan['name']}** - {plan['sales_count']} بار فروش" for i, plan in enumerate(plans, 1)])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return REPORTS_MENU


# --- Settings ---
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This can be a callback query or a message handler
    message = update.effective_message
    
    card_number = await db.get_setting('card_number') or "تنظیم نشده"
    card_holder = await db.get_setting('card_holder') or "تنظیم نشده"
    
    text = (f"⚙️ **تنظیمات ربات**\n\n"
            f"شماره کارت فعلی: `{card_number}`\n"
            f"صاحب حساب فعلی: `{card_holder}`\n\n"
            "برای تغییر هر مورد روی دکمه مربوطه کلیک کنید.")
            
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("ویرایش شماره کارت", callback_data="admin_edit_setting_card_number"),
         InlineKeyboardButton("ویرایش نام صاحب حساب", callback_data="admin_edit_setting_card_holder")],
        [InlineKeyboardButton("🔧 تنظیمات لینک پیشنهادی", callback_data="admin_link_settings")],
        [InlineKeyboardButton("📚 ویرایش راهنمای اتصال", callback_data="admin_edit_guide")]
    ])

    if update.callback_query:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU

# Settings Edit Flow (Separate Conversation)
async def edit_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    setting_key = query.data.split('admin_edit_setting_')[-1]
    context.user_data['setting_to_edit'] = setting_key
    
    prompt_map = {
        'card_number': "لطفا شماره کارت جدید را وارد کنید:",
        'card_holder': "لطفا نام جدید صاحب حساب را وارد کنید:"
    }
    prompt_text = prompt_map.get(setting_key, "مقدار جدید را وارد کنید:")
    
    await query.message.reply_text(prompt_text, reply_markup=keyboards.get_cancel_keyboard())
    return AWAIT_SETTING_VALUE

async def setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setting_key = context.user_data.get('setting_to_edit')
    if not setting_key:
        return await admin_conv_cancel(update, context)
        
    await db.set_setting(setting_key, update.message.text)
    await update.message.reply_text("✅ تنظیمات با موفقیت به‌روز شد.", reply_markup=keyboards.get_admin_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END
    
# Edit Guide Flow (Separate Conversation)
async def edit_guide_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    
    current_guide = await db.get_setting('connection_guide_text') or "هنوز تنظیم نشده است."
    
    await query.from_user.send_message(
        f"لطفاً متن جدید برای راهنمای اتصال را ارسال کنید.\n"
        f"شما می‌توانید از قالب‌بندی **Markdown** (مثل *bold* یا `code`) استفاده کنید.\n\n"
        f"**راهنمای فعلی:**\n{current_guide}",
        reply_markup=keyboards.get_cancel_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    return EDIT_GUIDE_TEXT

async def edit_guide_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_guide_text = update.message.text_markdown_v2
    await db.set_setting('connection_guide_text', new_guide_text)
    await update.message.reply_text(
        "✅ راهنمای اتصال با موفقیت به‌روزرسانی شد.",
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    return ConversationHandler.END


# --- User Management ---
async def user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "لطفا آیدی عددی یا یوزرنیم تلگرام (با یا بدون @) کاربری که می‌خواهید مدیریت کنید را وارد نمایید:",
        reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)
    )
    return MANAGE_USER_ID

async def manage_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    user_info = None
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    if user_input.isdigit(): 
        user_info = await db.get_user(int(user_input))
    else: 
        user_info = await db.get_user_by_username(user_input)
    
    if not user_info: 
        await update.message.reply_text("کاربری با این مشخصات یافت نشد.")
        return MANAGE_USER_ID
        
    context.user_data['target_user_id'] = user_info['user_id']
    
    info_text = (f"👤 مدیریت کاربر: `{user_info['user_id']}`\n"
                 f"🔹 یوزرنیم: @{user_info.get('username', 'N/A')}\n"
                 f"💰 موجودی: {user_info['balance']:.0f} تومان\n"
                 f"🚦 وضعیت: {'مسدود' if user_info['is_banned'] else 'فعال'}")
                 
    await update.message.reply_text(
        info_text,
        reply_markup=keyboards.get_user_management_action_keyboard(user_info['is_banned']),
        parse_mode=ParseMode.MARKDOWN
    )
    return MANAGE_USER_ACTION

async def manage_user_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    target_user_id = context.user_data.get('target_user_id')
    if not target_user_id: 
        return await back_to_admin_menu(update, context)

    if action in ["افزایش موجودی", "کاهش موجودی"]:
        context.user_data['manage_action'] = action
        await update.message.reply_text("لطفا مبلغ مورد نظر را به تومان وارد کنید:", reply_markup=keyboards.get_cancel_keyboard())
        return MANAGE_USER_AMOUNT
        
    elif "مسدود" in action or "آزاد" in action:
        user_info = await db.get_user(target_user_id)
        new_ban_status = not user_info['is_banned']
        await db.set_user_ban_status(target_user_id, new_ban_status)
        await update.message.reply_text(f"✅ وضعیت کاربر با موفقیت به '{'مسدود' if new_ban_status else 'فعال'}' تغییر کرد.")
        # Refresh the menu
        update.message.text = str(target_user_id)
        return await manage_user_id_received(update, context)

    elif action == "📜 سوابق خرید":
        history = await db.get_user_sales_history(target_user_id)
        if not history: 
            await update.message.reply_text("این کاربر تاکنون خریدی نداشته است.")
            return MANAGE_USER_ACTION
            
        response_message = "📜 **سوابق خرید کاربر:**\n\n"
        for sale in history:
            sale_date = datetime.strptime(sale['sale_date'], '%Y-%m-%d %H:%M:%S').strftime('%Y/%m/%d - %H:%M')
            response_message += (f"🔹 **{sale['plan_name'] or 'پلن حذف شده'}**\n"
                                 f" - قیمت: {sale['price']:.0f} تومان\n"
                                 f" - تاریخ: {sale_date}\n\n")
        await update.message.reply_text(response_message, parse_mode=ParseMode.MARKDOWN)
        return MANAGE_USER_ACTION
        
    else: 
        await update.message.reply_text("دستور نامعتبر است. لطفاً از دکمه‌ها استفاده کنید.")
        return MANAGE_USER_ACTION

async def manage_user_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        action = context.user_data['manage_action']
        target_user_id = context.user_data['target_user_id']
        is_add = True if action == "افزایش موجودی" else False
        
        await db.update_balance(target_user_id, amount if is_add else -amount)
        
        await update.message.reply_text(f"✅ مبلغ {amount:,.0f} تومان به حساب کاربر {'اضافه' if is_add else 'کسر'} شد.")
        
        # Refresh the menu
        update.message.text = str(target_user_id)
        return await manage_user_id_received(update, context)
    except (ValueError, TypeError): 
        await update.message.reply_text("لطفا مبلغ را به صورت عدد وارد کنید.")
        return MANAGE_USER_AMOUNT


# --- Broadcast ---
async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بخش ارسال پیام", reply_markup=keyboards.get_broadcast_menu_keyboard())
    return BROADCAST_MENU

async def broadcast_to_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا پیام خود را برای ارسال به همه کاربران وارد کنید:", reply_markup=keyboards.get_cancel_keyboard())
    return BROADCAST_MESSAGE

async def broadcast_to_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message'] = update.message
    total_users = (await db.get_stats())['total_users']
    await update.message.reply_text(
        f"آیا از ارسال این پیام به {total_users} کاربر مطمئن هستید؟",
        reply_markup=keyboards.get_broadcast_confirmation_keyboard()
    )
    return BROADCAST_CONFIRM

async def broadcast_to_all_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_to_send = context.user_data.get('broadcast_message')
    if not message_to_send:
        await update.message.reply_text("خطا: پیامی برای ارسال یافت نشد.", reply_markup=keyboards.get_admin_menu_keyboard())
        return ADMIN_MENU

    user_ids = await db.get_all_user_ids()
    sent_count, failed_count = 0, 0
    
    await update.message.reply_text(f"در حال ارسال پیام به {len(user_ids)} کاربر...", reply_markup=keyboards.get_admin_menu_keyboard())
    
    for user_id in user_ids:
        try: 
            await message_to_send.copy(chat_id=user_id)
            sent_count += 1
            await asyncio.sleep(0.05)  # Sleep for 50ms to avoid hitting rate limits
        except (Forbidden, BadRequest): 
            failed_count += 1
            
    await update.message.reply_text(f"✅ پیام همگانی با موفقیت ارسال شد.\n\nتعداد ارسال موفق: {sent_count}\nتعداد ارسال ناموفق: {failed_count}")
    context.user_data.clear()
    return ADMIN_MENU

async def broadcast_to_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا آیدی عددی کاربر هدف را وارد کنید:", reply_markup=keyboards.get_cancel_keyboard())
    return BROADCAST_TO_USER_ID

async def broadcast_to_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text)
        context.user_data['target_user_id'] = target_id
        await update.message.reply_text("آیدی ثبت شد. حالا پیامی که می‌خواهید برای این کاربر ارسال کنید را وارد نمایید:")
        return BROADCAST_TO_USER_MESSAGE
    except ValueError:
        await update.message.reply_text("لطفا یک آیدی عددی معتبر وارد کنید.")
        return BROADCAST_TO_USER_ID

async def broadcast_to_user_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = context.user_data.get('target_user_id')
    if not target_id:
        await update.message.reply_text("خطا: کاربر هدف مشخص نیست.", reply_markup=keyboards.get_admin_menu_keyboard())
        return ADMIN_MENU
        
    message_to_send = update.message
    try:
        await message_to_send.copy(chat_id=target_id)
        await update.message.reply_text("✅ پیام با موفقیت به کاربر ارسال شد.", reply_markup=keyboards.get_admin_menu_keyboard())
    except (Forbidden, BadRequest):
        await update.message.reply_text("❌ ارسال پیام ناموفق بود. احتمالا کاربر ربات را بلاک کرده یا آیدی اشتباه است.", reply_markup=keyboards.get_admin_menu_keyboard())
        
    context.user_data.clear()
    return ADMIN_MENU


# --- Backup & Restore ---
async def backup_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بخش پشتیبان‌گیری و بازیابی.", reply_markup=keyboards.get_backup_menu_keyboard())
    return BACKUP_MENU

async def send_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("در حال آماده‌سازی و ارسال فایل پشتیبان...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"backups/backup_{timestamp}.db"
    
    try:
        # Close the main connection before copying
        await db.close_db() 
        # Run synchronous shutil.copy in a separate thread
        await asyncio.to_thread(shutil.copy, db.DB_NAME, backup_filename)
        
        await context.bot.send_document(
            chat_id=update.effective_user.id,
            document=open(backup_filename, 'rb'),
            caption=f"پشتیبان دیتابیس - {timestamp}"
        )
    except Exception as e: 
        await update.message.reply_text(f"خطا در ایجاد یا ارسال فایل پشتیبان: {e}")
        logger.error(f"Backup file error: {e}", exc_info=True)
    finally:
        # Reopen the database connection
        await db.get_db_connection()
        if os.path.exists(backup_filename): 
            # Run synchronous os.remove in a separate thread
            await asyncio.to_thread(os.remove, backup_filename)
            
    return BACKUP_MENU

async def restore_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"⚠️ **اخطار:** بازیابی دیتابیس تمام اطلاعات فعلی را پاک می‌کند.\n"
        f"برای ادامه، فایل دیتابیس (`.db`) خود را ارسال کنید. برای لغو {CMD_CANCEL} را بزنید.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboards.get_cancel_keyboard()
    )
    return RESTORE_UPLOAD

async def restore_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or not document.file_name.endswith('.db'): 
        await update.message.reply_text("فرمت فایل نامعتبر است. لطفاً یک فایل `.db` ارسال کنید.")
        return RESTORE_UPLOAD
        
    file = await document.get_file()
    temp_path = os.path.join("backups", f"restore_temp_{datetime.now().timestamp()}.db")
    await file.download_to_drive(temp_path)
    
    if not is_valid_sqlite(temp_path):
        await update.message.reply_text("❌ فایل ارسالی یک دیتابیس SQLite معتبر نیست.", reply_markup=keyboards.get_admin_menu_keyboard())
        if os.path.exists(temp_path):
            await asyncio.to_thread(os.remove, temp_path)
        return ADMIN_MENU
        
    context.user_data['restore_path'] = temp_path
    keyboard = [[
        InlineKeyboardButton("✅ بله، مطمئنم", callback_data="admin_confirm_restore"),
        InlineKeyboardButton("❌ خیر، لغو کن", callback_data="admin_cancel_restore")
    ]]
    await update.message.reply_text(
        "**آیا از جایگزینی دیتابیس فعلی کاملاً مطمئن هستید؟ این عمل غیرقابل بازگشت است.**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return BACKUP_MENU


# --- Shutdown ---
async def shutdown_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ربات در حال خاموش شدن است...")
    logger.warning("Shutdown command received from admin.")
    await db.close_db()
    # Gently ask the application to shut down
    asyncio.create_task(context.application.shutdown())


# --- Conversation Handler Definitions ---
admin_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(f'^{BTN_ADMIN_PANEL}$') & filters.User(user_id=ADMIN_ID), admin_entry)],
    states={
        ADMIN_MENU: [
            MessageHandler(filters.Regex('^➕ مدیریت پلن‌ها$'), plan_management_menu),
            MessageHandler(filters.Regex('^📈 گزارش‌ها و آمار$'), reports_menu),
            MessageHandler(filters.Regex('^⚙️ تنظیمات$'), settings_menu),
            MessageHandler(filters.Regex('^💾 پشتیبان‌گیری$'), backup_restore_menu),
            MessageHandler(filters.Regex('^📩 ارسال پیام$'), broadcast_menu),
            MessageHandler(filters.Regex('^👥 مدیریت کاربران$'), user_management_menu),
            MessageHandler(filters.Regex('^🛑 خاموش کردن ربات$'), shutdown_bot),
        ],
        REPORTS_MENU: [
            MessageHandler(filters.Regex('^📊 آمار کلی$'), show_stats_report),
            MessageHandler(filters.Regex('^📈 گزارش فروش امروز$'), show_daily_report),
            MessageHandler(filters.Regex('^📅 گزارش فروش ۷ روز اخیر$'), show_weekly_report),
            MessageHandler(filters.Regex('^🏆 محبوب‌ترین پلن‌ها$'), show_popular_plans_report),
            MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu),
        ],
        PLAN_MENU: [
            MessageHandler(filters.Regex('^➕ افزودن پلن جدید$'), add_plan_start),
            MessageHandler(filters.Regex('^📋 لیست پلن‌ها$'), list_plans_admin),
            MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu),
        ],
        PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_name_received)],
        PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_price_received)],
        PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_days_received)],
        PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_gb_received)],
        MANAGE_USER_ID: [
            MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu),
            MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_id_received)
        ],
        MANAGE_USER_ACTION: [
            MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu),
            MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_action_handler)
        ],
        MANAGE_USER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_amount_received)],
        BROADCAST_MENU: [
            MessageHandler(filters.Regex('^ارسال به همه کاربران$'), broadcast_to_all_start),
            MessageHandler(filters.Regex('^ارسال به کاربر خاص$'), broadcast_to_user_start),
            MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu)
        ],
        BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_to_all_confirm)],
        BROADCAST_CONFIRM: [MessageHandler(filters.Regex('^بله، ارسال کن$'), broadcast_to_all_send), MessageHandler(filters.Regex('^خیر، لغو کن$'), admin_generic_cancel)],
        BROADCAST_TO_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_to_user_id_received)],
        BROADCAST_TO_USER_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_to_user_message_received)],
        BACKUP_MENU: [
            MessageHandler(filters.Regex('^📥 دریافت فایل پشتیبان$'), send_backup_file),
            MessageHandler(filters.Regex('^📤 بارگذاری فایل پشتیبان$'), restore_start),
            MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu),
        ],
        RESTORE_UPLOAD: [MessageHandler(filters.Document.FileExtension("db"), restore_receive_file)]
    },
    fallbacks=[
        MessageHandler(filters.Regex(f'^{BTN_EXIT_ADMIN_PANEL}$'), exit_admin_panel),
        CommandHandler('cancel', admin_generic_cancel),
    ],
    per_user=True, per_chat=True, allow_reentry=True
)

edit_plan_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(edit_plan_start, pattern="^admin_edit_plan_")],
    states={
        EDIT_PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_plan_name_received), CommandHandler('skip', skip_edit_plan_name)],
        EDIT_PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_plan_price_received), CommandHandler('skip', skip_edit_plan_price)],
        EDIT_PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_plan_days_received), CommandHandler('skip', skip_edit_plan_days)],
        EDIT_PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_plan_gb_received), CommandHandler('skip', skip_edit_plan_gb)],
    },
    fallbacks=[CommandHandler('cancel', admin_conv_cancel)],
    per_user=True, per_chat=True,
)

settings_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(edit_setting_start, pattern="^admin_edit_setting_")],
    states={AWAIT_SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_value_received)]},
    fallbacks=[CommandHandler('cancel', admin_conv_cancel)],
    per_user=True, per_chat=True,
)

edit_guide_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(edit_guide_start, pattern="^admin_edit_guide$")],
    states={EDIT_GUIDE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_guide_received)]},
    fallbacks=[CommandHandler('cancel', admin_conv_cancel)],
    per_user=True, per_chat=True
)
