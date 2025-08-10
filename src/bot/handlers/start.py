# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import database as db
from bot.keyboards import get_main_menu_keyboard, get_admin_menu_keyboard
from bot.constants import ADMIN_MENU
from config import SUPPORT_USERNAME, REFERRAL_BONUS_AMOUNT

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username)

    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].split('_')[1])
            if referrer_id != user.id:
                db.set_referrer(user.id, referrer_id)
        except (ValueError, IndexError):
            logger.warning(f"Invalid referral link: {context.args[0]}")

    user_info = db.get_user(user.id)
    if user_info and user_info.get('is_banned'):
        await update.message.reply_text("شما از استفاده از این ربات منع شده‌اید.")
        return ConversationHandler.END

    await update.message.reply_text("👋 به ربات خوش آمدید!", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END

async def user_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END

async def admin_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU

async def admin_conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
    return ConversationHandler.END

async def show_account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)
    kb = [[InlineKeyboardButton("💳 شارژ حساب", callback_data="user_start_charge")]]
    text = (
        f"👤 **اطلاعات حساب شما**\n\n"
        f"▫️ شناسه عددی: `{user_id}`\n"
        f"▫️ موجودی کیف پول: **{user['balance']:.0f} تومان**"
    )
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if SUPPORT_USERNAME:
        await update.message.reply_text(f"📞 برای پشتیبانی پیام دهید: @{SUPPORT_USERNAME}")
    else:
        await update.message.reply_text("📞 پشتیبانی در دسترس است.")

async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    guide = db.get_setting("connection_guide")
    if not guide:
        guide = (
            "📚 راهنمای اتصال\n\n"
            "1) اپ مناسب (V2Ray/Clash/SingBox) را نصب کنید.\n"
            "2) از ربات «⚡ دریافت لینک پیش‌فرض» را بگیرید.\n"
            "3) لینک را در اپ وارد کنید و متصل شوید.\n"
            "سؤال داشتید؟ از «📞 پشتیبانی» بپرسید."
        )
    await update.message.reply_text(guide, disable_web_page_preview=True)

async def show_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    bonus_str = db.get_setting('referral_bonus_amount')
    try:
        bonus = int(float(bonus_str)) if bonus_str is not None else REFERRAL_BONUS_AMOUNT
    except (ValueError, TypeError):
        bonus = REFERRAL_BONUS_AMOUNT

    text = (
        f"🎁 دوستان خود را دعوت کنید و هدیه بگیرید!\n\n"
        f"با لینک اختصاصی زیر دوستان خود را دعوت کنید:\n"
        f"`{referral_link}`\n\n"
        f"با اولین خرید دوست شما، مبلغ **{bonus:,.0f} تومان** به کیف پول شما و **{bonus:,.0f} تومان** به کیف پول دوستتان اضافه می‌شود."
    )
    await update.message.reply_text(text, parse_mode="Markdown")