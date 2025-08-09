# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from bot.keyboards import get_admin_menu_keyboard
from bot.constants import AWAIT_SETTING_VALUE, CMD_CANCEL, ADMIN_MENU
import database as db
from config import REFERRAL_BONUS_AMOUNT

AVAILABLE_LINK_TYPES = ["sub", "auto", "sub64", "singbox", "xray", "clashmeta", "clash"]
BACKUP_INTERVALS = {"هرگز": 0, "هر 6 ساعت": 6, "هر 12 ساعت": 12, "هر 24 ساعت": 24, "هر 48 ساعت": 48}

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card_number = db.get_setting('card_number') or "تنظیم نشده"
    card_holder = db.get_setting('card_holder') or "تنظیم نشده"
    referral_bonus = db.get_setting('referral_bonus_amount') or str(REFERRAL_BONUS_AMOUNT)
    default_link = db.get_setting('default_sub_link_type') or "sub"
    
    daily_report = db.get_setting('daily_report_enabled') == '1'
    weekly_report = db.get_setting('weekly_report_enabled') == '1'
    backup_interval = int(db.get_setting('auto_backup_interval_hours') or 0)
    
    backup_status = "غیرفعال"
    for name, hours in BACKUP_INTERVALS.items():
        if hours == backup_interval:
            backup_status = name
            break
            
    text = (
        f"⚙️ **تنظیمات ربات**\n\n"
        f"▫️ شماره کارت: `{card_number}`\n"
        f"▫️ صاحب حساب: `{card_holder}`\n"
        f"▫️ هدیه معرفی: `{referral_bonus}` تومان\n"
        f"▫️ لینک پیش‌فرض: `{default_link}`\n\n"
        f"▫️ گزارش روزانه: **{'✅ فعال' if daily_report else '❌ غیرفعال'}**\n"
        f"▫️ گزارش هفتگی: **{'✅ فعال' if weekly_report else '❌ غیرفعال'}**\n"
        f"▫️ بکاپ خودکار: **{backup_status}**\n\n"
        "برای تغییر هر مورد، روی دکمه مربوطه کلیک کنید."
    )
    kb = [
        [InlineKeyboardButton("ویرایش شماره کارت", callback_data="admin_edit_setting_card_number"),
         InlineKeyboardButton("ویرایش نام صاحب حساب", callback_data="admin_edit_setting_card_holder")],
        [InlineKeyboardButton("ویرایش مبلغ هدیه", callback_data="admin_edit_setting_referral_bonus_amount")],
        [InlineKeyboardButton("ویرایش لینک پیش‌فرض", callback_data="edit_default_link_type")],
        [InlineKeyboardButton("تغییر وضعیت گزارش روزانه", callback_data="toggle_report_daily"),
         InlineKeyboardButton("تغییر وضعیت گزارش هفتگی", callback_data="toggle_report_weekly")],
        [InlineKeyboardButton("تنظیم بکاپ خودکار", callback_data="edit_auto_backup")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def edit_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    key = q.data.split('admin_edit_setting_')[-1]
    context.user_data['setting_to_edit'] = key
    prompts = {
        'card_number': "شماره کارت جدید را وارد کنید:",
        'card_holder': "نام جدید صاحب حساب را وارد کنید:",
        'referral_bonus_amount': "مبلغ هدیه معرفی (تومان) را وارد کنید:"
    }
    text = prompts.get(key)
    if not text:
        await q.message.edit_text("تنظیمات ناشناخته.")
        return ConversationHandler.END
    await q.message.reply_text(text, reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return AWAIT_SETTING_VALUE

async def setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.get('setting_to_edit')
    if not key:
        from .common import admin_conv_cancel
        return await admin_conv_cancel(update, context)
    value = update.message.text.strip()
    if key == 'referral_bonus_amount':
        try:
            value = str(int(float(value)))
        except (ValueError, TypeError):
            await update.message.reply_text("لطفاً مبلغ را به صورت عدد صحیح وارد کنید (مثلاً 5000).")
            return AWAIT_SETTING_VALUE
    db.set_setting(key, value)
    await update.message.reply_text("✅ تنظیمات با موفقیت به‌روزرسانی شد.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear()
    return ADMIN_MENU

async def edit_default_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    keyboard = []
    row = []
    for link_type in AVAILABLE_LINK_TYPES:
        row.append(InlineKeyboardButton(link_type.replace("sub", "V2ray ").replace("meta", " Meta").title(), callback_data=f"set_default_link_{link_type}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ بازگشت به تنظیمات", callback_data="back_to_settings")])
    await q.edit_message_text("لطفاً نوع لینک پیش‌فرض جدید را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def set_default_link_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    link_type = q.data.split('set_default_link_')[-1]
    if link_type in AVAILABLE_LINK_TYPES:
        db.set_setting('default_sub_link_type', link_type)
        await q.answer("لینک پیش‌فرض با موفقیت تغییر کرد!", show_alert=True)
        await settings_menu(update, context)
    else:
        await q.answer("نوع لینک نامعتبر است.", show_alert=True)

async def toggle_report_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    report_type = q.data.split('_')[-1]
    setting_key = f"{report_type}_report_enabled"
    current_status = db.get_setting(setting_key)
    new_status = '0' if current_status == '1' else '1'
    db.set_setting(setting_key, new_status)
    await q.answer(f"گزارش {report_type} {'فعال' if new_status == '1' else 'غیرفعال'} شد. تغییرات در دوره بعدی گزارش‌دهی اعمال می‌شود.", show_alert=True)
    await settings_menu(update, context)

async def edit_auto_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"set_backup_interval_{hours}")]
        for name, hours in BACKUP_INTERVALS.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ بازگشت به تنظیمات", callback_data="back_to_settings")])
    await q.edit_message_text("لطفاً دوره زمانی بکاپ خودکار را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def set_backup_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    interval_hours = int(q.data.split('_')[-1])
    db.set_setting('auto_backup_interval_hours', str(interval_hours))
    await q.answer("تنظیمات بکاپ خودکار ذخیره شد. برای اعمال، ربات باید ری‌استارت شود.", show_alert=True)
    await settings_menu(update, context)