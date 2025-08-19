# -*- coding: utf-8 -*-

import uuid
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from bot.constants import (
    ADMIN_MENU, BTN_BACK_TO_ADMIN_MENU, CMD_CANCEL, GIFT_CODES_MENU,
    PROMO_GET_CODE, PROMO_GET_PERCENT, PROMO_GET_MAX_USES, PROMO_GET_EXPIRES, PROMO_GET_FIRST_PURCHASE
)
from bot import utils
import database as db

CREATE_GIFT_AMOUNT = 201

# --- Helpers ---
def _gift_root_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["🎁 مدیریت کدهای هدیه", "💳 مدیریت کدهای تخفیف"], [BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)

def _gift_codes_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["➕ ساخت کد هدیه جدید", "📋 لیست کدهای هدیه"], ["بازگشت به منوی کدها"]], resize_keyboard=True)

def _promo_codes_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["➕ ساخت کد تخفیف جدید", "📋 لیست کدهای تخفیف"], ["بازگشت به منوی کدها"]], resize_keyboard=True)

# --- منوی اصلی مدیریت کدها ---
async def gift_code_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text("بخش مدیریت کدها", reply_markup=_gift_root_menu_keyboard())
    return GIFT_CODES_MENU

# --- زیرمنوی کدهای هدیه (شارژ) ---
async def admin_gift_codes_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text("🎁 بخش مدیریت کدهای هدیه", reply_markup=_gift_codes_menu_keyboard())
    return GIFT_CODES_MENU

async def list_gift_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    codes = db.get_all_gift_codes()
    if not codes:
        await em.reply_text("هیچ کد هدیه‌ای تا به حال ساخته نشده است.", reply_markup=_gift_codes_menu_keyboard())
        return GIFT_CODES_MENU
    await em.reply_text("📋 لیست کدهای هدیه:", parse_mode="Markdown", reply_markup=_gift_codes_menu_keyboard())
    for code in codes:
        status = "✅ استفاده شده" if code.get('is_used') else "🟢 فعال"
        used_by = f" (توسط: `{code.get('used_by')}`)" if code.get('used_by') else ""
        amount_str = utils.format_toman(code.get('amount', 0), persian_digits=True)
        text = f"`{code.get('code')}` - **{amount_str}** - {status}{used_by}"
        keyboard = None
        if not code.get('is_used'):
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_gift_code_{code.get('code')}")]])
        await em.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    return GIFT_CODES_MENU

async def delete_gift_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    code_to_delete = q.data.split('delete_gift_code_')[-1]
    if db.delete_gift_code(code_to_delete):
        await q.edit_message_text(f"✅ کد `{code_to_delete}` با موفقیت حذف شد.", parse_mode=ParseMode.MARKDOWN)
    else:
        await q.edit_message_text(f"❌ خطا: کد `{code_to_delete}` یافت نشد یا قبلاً حذف شده بود.", parse_mode=ParseMode.MARKDOWN)
    return GIFT_CODES_MENU

async def create_gift_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text(
        "لطفاً مبلغ کد هدیه را به تومان وارد کنید:",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
    )
    return CREATE_GIFT_AMOUNT

async def create_gift_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.effective_message.text or "").strip().replace(",", ".")
    try:
        amount = float(txt)
        if amount <= 0: raise ValueError
    except (ValueError, TypeError):
        await update.effective_message.reply_text("❗️ لطفاً یک مبلغ عددی و مثبت وارد کنید.")
        return CREATE_GIFT_AMOUNT
    code = str(uuid.uuid4()).split('-')[0].upper()
    if db.create_gift_code(code, amount):
        amount_str = utils.format_toman(amount, persian_digits=True)
        await update.effective_message.reply_text(
            f"✅ کد هدیه با موفقیت ساخته شد:\n\n`{code}`\n\nمبلغ: **{amount_str}**",
            parse_mode="Markdown",
            reply_markup=_gift_codes_menu_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            "❌ در ساخت کد هدیه خطایی رخ داد (احتمالاً کد تکراری است). لطفاً دوباره تلاش کنید.",
            reply_markup=_gift_codes_menu_keyboard()
        )
    return ConversationHandler.END

async def cancel_create_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("❌ عملیات لغو شد.", reply_markup=_gift_codes_menu_keyboard())
    return ConversationHandler.END

# --- زیرمنوی کدهای تخفیف ---
async def admin_promo_codes_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text("💳 بخش مدیریت کدهای تخفیف", reply_markup=_promo_codes_menu_keyboard())
    return GIFT_CODES_MENU

async def list_promo_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    codes = db.get_all_promo_codes()
    if not codes:
        await em.reply_text("هیچ کد تخفیفی تعریف نشده است.", reply_markup=_promo_codes_menu_keyboard())
        return GIFT_CODES_MENU
    await em.reply_text("📋 لیست کدهای تخفیف:", reply_markup=_promo_codes_menu_keyboard())
    for p in codes:
        status = "🟢 فعال" if p['is_active'] else "🔴 غیرفعال"
        exp = utils.parse_date_flexible(p['expires_at']).strftime('%Y-%m-%d') if p['expires_at'] else "همیشگی"
        uses = f"{p['used_count']}/{p['max_uses']}" if p['max_uses'] > 0 else f"{p['used_count']}"
        text = f"`{p['code']}` | {p['percent']}% | استفاده: {uses} | انقضا: {exp} | فقط خرید اول: {'بله' if p['first_purchase_only'] else 'خیر'} | {status}"
        await em.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return GIFT_CODES_MENU

# کانورسیشن ساخت کد تخفیف
async def create_promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("کد تخفیف را وارد کنید (مثلاً SUMMER20):", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return PROMO_GET_CODE

async def promo_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = (update.message.text or "").strip().upper()
    if db.get_promo_code(code):
        await update.message.reply_text("این کد قبلاً استفاده شده. لطفاً کد دیگری وارد کنید.")
        return PROMO_GET_CODE
    context.user_data['promo'] = {'code': code}
    await update.message.reply_text("درصد تخفیف را وارد کنید (مثلاً 30):")
    return PROMO_GET_PERCENT

async def promo_percent_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        percent = int(update.message.text)
        if not (0 < percent <= 100): raise ValueError
    except Exception:
        await update.message.reply_text("لطفاً یک عدد بین 1 تا 100 وارد کنید.")
        return PROMO_GET_PERCENT
    context.user_data['promo']['percent'] = percent
    await update.message.reply_text("حداکثر تعداد استفاده را وارد کنید (برای نامحدود 0):")
    return PROMO_GET_MAX_USES

async def promo_max_uses_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        max_uses = int(update.message.text)
        if max_uses < 0: raise ValueError
    except Exception:
        await update.message.reply_text("لطفاً یک عدد صحیح و مثبت (یا 0) وارد کنید.")
        return PROMO_GET_MAX_USES
    context.user_data['promo']['max_uses'] = max_uses
    await update.message.reply_text("تاریخ انقضا را وارد کنید (فرمت: 2025-12-31). برای نامحدود /skip بزنید.")
    return PROMO_GET_EXPIRES

async def promo_expires_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        expires_at = datetime.strptime(update.message.text, '%Y-%m-%d').isoformat()
    except Exception:
        await update.message.reply_text("فرمت تاریخ نامعتبر است. لطفاً به شکل YYYY-MM-DD وارد کنید.")
        return PROMO_GET_EXPIRES
    context.user_data['promo']['expires_at'] = expires_at
    await update.message.reply_text("آیا این کد فقط برای خرید اول باشد؟", reply_markup=ReplyKeyboardMarkup([['بله'], ['خیر']], resize_keyboard=True))
    return PROMO_GET_FIRST_PURCHASE

async def promo_skip_expires(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['promo']['expires_at'] = None
    await update.message.reply_text("آیا این کد فقط برای خرید اول باشد؟", reply_markup=ReplyKeyboardMarkup([['بله'], ['خیر']], resize_keyboard=True))
    return PROMO_GET_FIRST_PURCHASE

async def promo_first_purchase_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    first_only = update.message.text == 'بله'
    promo = context.user_data['promo']
    db.add_promo_code(promo['code'], promo['percent'], promo['max_uses'], promo.get('expires_at'), first_only)
    await update.message.reply_text(f"✅ کد تخفیف `{promo['code']}` با موفقیت ساخته شد.", parse_mode=ParseMode.MARKDOWN, reply_markup=_promo_codes_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_promo_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=_promo_codes_menu_keyboard())
    return ConversationHandler.END