# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode

import database as db
from hiddify_api import HiddifyAPI
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUBSCRIPTION_LINK
from bot import utils
from bot.constants import GET_CUSTOM_NAME, CMD_CANCEL, CMD_SKIP
from bot.handlers.start import get_main_keyboard

logger = logging.getLogger(__name__)
hiddify = HiddifyAPI(PANEL_DOMAIN, ADMIN_PATH, API_KEY)

def _maint_on() -> bool:
    val = db.get_setting("maintenance_enabled")
    return str(val).lower() in ("1", "true", "on", "yes")

def _maint_msg() -> str:
    return db.get_setting("maintenance_message") or "⛔️ ربات در حال بروزرسانی است. لطفاً کمی بعد مراجعه کنید."

async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()
        send_func = q.edit_message_text
    else:
        send_func = update.message.reply_text
    if _maint_on():
        await send_func(_maint_msg())
        return
    categories = db.get_plan_categories()
    if not categories:
        await send_func("در حال حاضر پلنی برای خرید موجود نیست.")
        return
    text = "🛍️ لطفاً دسته‌بندی مورد نظر خود را انتخاب کنید:"
    keyboard = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(cat, callback_data=f"user_cat_{cat}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    await send_func(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_plans_in_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    category = q.data.replace("user_cat_", "")
    plans = db.list_plans(only_visible=True, category=category)
    if not plans:
        await q.edit_message_text("در این دسته‌بندی پلنی یافت نشد.")
        return
    text = f"پلن‌های دسته‌بندی «{category}»:"
    kb = []
    for p in plans:
        volume_text = f"{p['gb']} گیگ" if p['gb'] > 0 else "نامحدود"
        title = f"{p['name']} | {p['days']} روزه {volume_text} - {p['price']:.0f} تومان"
        kb.append([InlineKeyboardButton(title, callback_data=f"user_buy_{p['plan_id']}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت به دسته‌بندی‌ها", callback_data="back_to_cats")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if _maint_on():
        await q.answer(_maint_msg(), show_alert=True)
        return ConversationHandler.END
    try: plan_id = int(q.data.split('_')[-1])
    except Exception:
        await q.answer("شناسه پلن نامعتبر است.", show_alert=True)
        return ConversationHandler.END
    plan = db.get_plan(plan_id)
    if not plan or not plan.get('is_visible', 1):
        await q.answer("این پلن در دسترس نیست.", show_alert=True)
        return ConversationHandler.END
    context.user_data['buy_plan_id'] = plan_id
    try: await q.message.delete()
    except Exception: pass
    await context.bot.send_message(
        chat_id=q.from_user.id,
        text="لطفاً نام دلخواه برای سرویس‌تان را وارد کنید.\nبرای رد شدن از این مرحله، /skip را بزنید.",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
    )
    return GET_CUSTOM_NAME

async def get_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("لطفاً یک نام معتبر وارد کنید یا /skip بزنید.")
        return GET_CUSTOM_NAME
    if db.get_service_by_name(update.effective_user.id, name):
        await update.message.reply_text("⚠️ شما قبلاً سرویسی با این نام داشته‌اید. لطفاً نام دیگری انتخاب کنید.")
        return GET_CUSTOM_NAME
    return await _process_purchase(update, context, custom_name=name)

async def skip_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _process_purchase(update, context, custom_name="")

async def _process_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_name: str):
    user_id = update.effective_user.id
    username = update.effective_user.username
    plan_id = context.user_data.get('buy_plan_id')
    plan = db.get_plan(plan_id) if plan_id else None
    if not plan:
        await update.message.reply_text("❌ پلن انتخاب‌شده نامعتبر است. لطفاً دوباره تلاش کنید.", reply_markup=get_main_keyboard(user_id))
        context.user_data.clear()
        return ConversationHandler.END
    txn_id = db.initiate_purchase_transaction(user_id, plan_id)
    if not txn_id:
        await update.message.reply_text(
            "❌ موجودی کافی نیست. لطفاً ابتدا حسابتان را شارژ کنید.",
            reply_markup=ReplyKeyboardMarkup([["💰 موجودی و شارژ حساب"]], resize_keyboard=True)
        )
        context.user_data.clear()
        return ConversationHandler.END
    try:
        await update.message.reply_text("⏳ در حال ایجاد سرویس شما...", reply_markup=get_main_keyboard(user_id))
        final_name = custom_name or f"سرویس {plan['gb']} گیگ"
        note = f"tg:@{username}|id:{user_id}" if username else f"tg:id:{user_id}"
        new_uuid = hiddify.add_user(final_name, plan['gb'], plan['days'], note)
        if not new_uuid:
            raise RuntimeError("Provisioning failed or no uuid returned.")
        db.finalize_purchase_transaction(txn_id, new_uuid, final_name)
        user_data = hiddify.get_user(new_uuid)
        if user_data:
            message_title = "🎉 سرویس شما با موفقیت ساخته شد!"
            message_text = utils.create_service_info_message(user_data, SUBSCRIPTION_LINK, title=message_title)
            await context.bot.send_message(chat_id=user_id, text=message_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("✅ خرید شما با موفقیت انجام شد، اما در دریافت اطلاعات سرویس مشکلی پیش آمد. لطفاً از منوی «سرویس‌های من» آن را مشاهده کنید.")
    except Exception as e:
        logger.error("Purchase failed for user %s plan %s: %s", user_id, plan_id, e, exc_info=True)
        db.cancel_purchase_transaction(txn_id)
        await update.message.reply_text("❌ خطا در ایجاد سرویس. لطفاً بعداً دوباره تلاش کنید یا به پشتیبانی اطلاع دهید.")
    context.user_data.clear()
    return ConversationHandler.END