# ====== Broadcast handlers (add to admin/users.py) ======
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError

from bot.constants import (
    BROADCAST_MENU, BROADCAST_MESSAGE, BROADCAST_CONFIRM,
    BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE,
    BTN_BACK_TO_ADMIN_MENU
)
import database as db

logger = logging.getLogger(__name__)

def _broadcast_menu_keyboard():
    return ReplyKeyboardMarkup(
        [["ارسال به همه کاربران", "ارسال به کاربر خاص"], [BTN_BACK_TO_ADMIN_MENU]],
        resize_keyboard=True
    )

async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بخش ارسال پیام", reply_markup=_broadcast_menu_keyboard())
    return BROADCAST_MENU

# --- Broadcast to all users ---
async def broadcast_to_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["broadcast_mode"] = "all"
    await update.message.reply_text(
        "متن/رسانه پیام همگانی را بفرستید:",
        reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)
    )
    return BROADCAST_MESSAGE

async def broadcast_to_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message'] = update.message
    total_users = db.get_all_user_ids()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید ارسال", callback_data="broadcast_confirm_yes"),
         InlineKeyboardButton("❌ انصراف", callback_data="broadcast_confirm_no")]
    ])
    await update.message.reply_text(
        f"پیش‌نمایش ثبت شد. ارسال به {len(total_users)} کاربر انجام شود؟",
        reply_markup=keyboard
    )
    return BROADCAST_CONFIRM

async def broadcast_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.endswith("no"):
        try:
            await q.edit_message_text("ارسال همگانی لغو شد.", reply_markup=None)
        except Exception:
            pass
        context.user_data.clear()
        return ConversationHandler.END

    # تایید = ارسال
    msg = context.user_data.get("broadcast_message")
    if not msg:
        await q.edit_message_text("خطا: پیامی برای ارسال یافت نشد.", reply_markup=None)
        context.user_data.clear()
        return ConversationHandler.END

    user_ids = db.get_all_user_ids()
    ok = fail = 0
    try:
        await q.edit_message_text(f"در حال ارسال به {len(user_ids)} کاربر... ⏳", reply_markup=None)
    except Exception:
        pass

    for uid in user_ids:
        try:
            await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            ok += 1
        except RetryAfter as e:
            await asyncio.sleep(getattr(e, "retry_after", 1) + 1)
            try:
                await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
                ok += 1
            except Exception:
                fail += 1
        except (Forbidden, BadRequest, TimedOut, NetworkError):
            fail += 1
        except Exception as e:
            logger.warning("Broadcast send failed to %s: %s", uid, e)
            fail += 1
        await asyncio.sleep(0.05)

    summary = f"ارسال همگانی تمام شد.\nموفق: {ok}\nناموفق: {fail}\nکل: {len(user_ids)}"
    try:
        await q.edit_message_text(summary, reply_markup=None)
    except Exception:
        await q.from_user.send_message(summary)

    context.user_data.clear()
    return ConversationHandler.END

# --- Broadcast to a specific user ---
async def broadcast_to_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["broadcast_mode"] = "single"
    await update.message.reply_text(
        "شناسه عددی کاربر را بفرستید:",
        reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)
    )
    return BROADCAST_TO_USER_ID

async def broadcast_to_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        if uid <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("شناسه معتبر نیست. یک عدد مثبت بفرستید.")
        return BROADCAST_TO_USER_ID

    context.user_data["target_user_id"] = uid
    await update.message.reply_text("متن/رسانه پیام را بفرستید:", reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True))
    return BROADCAST_TO_USER_MESSAGE

async def broadcast_to_user_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = context.user_data.get("target_user_id")
    if not uid:
        await update.message.reply_text("شناسه کاربر مشخص نیست.")
        context.user_data.clear()
        return ConversationHandler.END

    msg = update.message
    try:
        await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
        await update.message.reply_text("✅ پیام برای کاربر ارسال شد.")
    except Exception as e:
        await update.message.reply_text("❌ ارسال ناموفق بود. احتمالاً کاربر بات را مسدود کرده یا آیدی اشتباه است.")
    context.user_data.clear()
    return ConversationHandler.END