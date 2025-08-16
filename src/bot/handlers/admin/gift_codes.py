# -*- coding: utf-8 -*-
"""
Admin handlers for creating, listing, and deleting gift codes.
"""

import uuid
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bot import constants
import database as db

def _get_gift_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns the keyboard for the gift code management menu."""
    return ReplyKeyboardMarkup([
        ["➕ ساخت کد هدیه جدید", "📋 لیست کدهای هدیه"],
        [constants.BTN_BACK_TO_ADMIN_MENU]
    ], resize_keyboard=True)

async def gift_code_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the gift code management menu."""
    await update.message.reply_text(
        "🎁 بخش مدیریت کدهای هدیه",
        reply_markup=_get_gift_menu_keyboard()
    )
    return constants.ADMIN_MENU

async def list_gift_codes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all existing gift codes with their status."""
    codes = await db.get_all_gift_codes()
    if not codes:
        await update.message.reply_text("هیچ کد هدیه‌ای تا به حال ساخته نشده است.")
        return

    await update.message.reply_text("📋 **لیست کدهای هدیه:**", parse_mode="Markdown")
    
    # Send codes in batches to avoid hitting message limits
    batch = []
    for code in codes:
        status = "✅ استفاده شده" if code['is_used'] else "🟢 فعال"
        used_by_info = f" (توسط: `{code['used_by']}`)" if code.get('used_by') else ""
        text = f"`{code['code']}` - **{code['amount']:,.0f} تومان** - {status}{used_by_info}"
        
        keyboard = None
        if not code['is_used']:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🗑️ حذف کد", callback_data=f"delete_gift_code_{code['code']}")
            ]])
        
        # Send message with its keyboard immediately
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def delete_gift_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the deletion of an unused gift code."""
    query = update.callback_query
    await query.answer()
    code_to_delete = query.data.split('delete_gift_code_')[-1]

    if await db.delete_gift_code(code_to_delete):
        await query.edit_message_text(f"✅ کد `{code_to_delete}` با موفقیت حذف شد.", parse_mode="Markdown")
    else:
        # Give a more helpful error message
        await query.answer("❌ این کد یافت نشد. ممکن است قبلاً حذف شده باشد.", show_alert=True)
        await query.edit_message_text(query.message.text + "\n\n-- 삭 (حذف شد) --")


async def create_gift_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation for creating a new gift code."""
    await update.message.reply_text(
        "لطفاً مبلغ کد هدیه جدید را به تومان وارد کنید (فقط عدد):",
        reply_markup=ReplyKeyboardMarkup([[constants.CMD_CANCEL]], resize_keyboard=True)
    )
    return constants.CREATE_GIFT_AMOUNT

async def create_gift_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the amount, creates the gift code, and ends the conversation."""
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError("Amount must be positive.")
    except (ValueError, TypeError):
        await update.message.reply_text("❌ مبلغ نامعتبر است. لطفاً یک عدد مثبت وارد کنید (مثلاً: 50000).")
        return constants.CREATE_GIFT_AMOUNT

    # Generate a unique, easy-to-read code
    code = f"GIFT-{str(uuid.uuid4()).split('-')[0].upper()}"

    if await db.create_gift_code(code, amount):
        await update.message.reply_text(
            f"✅ کد هدیه با موفقیت ساخته شد:\n\n`{code}`\n\n**مبلغ:** {amount:,.0f} تومان",
            parse_mode="Markdown",
            reply_markup=_get_gift_menu_keyboard()
        )
    else:
        # This is very unlikely with UUID, but handled for robustness
        await update.message.reply_text(
            "❌ در ساخت کد هدیه خطایی رخ داد. لطفاً دوباره تلاش کنید.",
            reply_markup=_get_gift_menu_keyboard()
        )

    return constants.ADMIN_MENU # Return to the main admin menu state within the conversation
