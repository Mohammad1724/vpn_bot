# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

import database as db
import hiddify_api
from bot.constants import GET_CUSTOM_NAME, CMD_CANCEL, CMD_SKIP
from bot.handlers import user_services as us_h

logger = logging.getLogger(__name__)

# ===== Helpers =====
def _maint_on() -> bool:
    val = db.get_setting("maintenance_enabled")
    return str(val).lower() in ("1", "true", "on", "yes")

def _maint_msg() -> str:
    return db.get_setting("maintenance_message") or "⛔️ ربات در حال بروزرسانی است. لطفاً کمی بعد مراجعه کنید."

# ===== Public handlers =====
async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _maint_on():
        await update.message.reply_text(_maint_msg())
        return
    plans = db.list_plans(only_visible=True)
    if not plans:
        await update.message.reply_text("در حال حاضر پلنی برای خرید موجود نیست.")
        return
    text = "🛍️ لطفاً یکی از پلن‌های زیر را برای خرید انتخاب کنید:"
    kb = []
    for p in plans:
        title = f"{p['name']} | {p['price']:.0f} تومان | {p['days']} روز | {p['gb']} گیگ"
        kb.append([InlineKeyboardButton(title, callback_data=f"user_buy_{p['plan_id']}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if _maint_on():
        await q.answer(_maint_msg(), show_alert=True)
        return ConversationHandler.END

    try:
        plan_id = int(q.data.split('_')[-1])
    except Exception:
        await q.answer("شناسه پلن نامعتبر است.", show_alert=True)
        return ConversationHandler.END

    plan = db.get_plan(plan_id)
    if not plan or not plan.get('is_visible', 1):
        await q.answer("این پلن در دسترس نیست.", show_alert=True)
        return ConversationHandler.END

    context.user_data['buy_plan_id'] = plan_id
    try:
        await q.message.delete()
    except Exception:
        pass

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
    plan_id = context.user_data.get('buy_plan_id')
    plan = db.get_plan(plan_id) if plan_id else None

    if not plan:
        await update.message.reply_text("❌ پلن انتخاب‌شده نامعتبر است. لطفاً دوباره تلاش کنید.")
        context.user_data.clear()
        return ConversationHandler.END

    txn_id = db.initiate_purchase_transaction(user_id, plan_id)
    if not txn_id:
        await update.message.reply_text(
            "❌ موجودی کافی نیست. لطفاً ابتدا حسابتان را شارژ کنید.",
            reply_markup=ReplyKeyboardMarkup([["💰 موجودی و شارژ"]], resize_keyboard=True)
        )
        context.user_data.clear()
        return ConversationHandler.END

    try:
        await update.message.reply_text("⏳ در حال ایجاد سرویس شما...")

        final_name = custom_name or f"سرویس {plan['gb']} گیگ"

        provision = await hiddify_api.create_hiddify_user(
            plan_days=plan['days'],
            plan_gb=plan['gb'],
            device_limit=0,
            user_telegram_id=user_id,
            custom_name=final_name
        )
        if not provision or not provision.get("uuid"):
            raise RuntimeError("Provisioning failed or no uuid returned.")

        sub_uuid = provision["uuid"]
        sub_link = ""  # لینک در send_service_details ساخته می‌شود
        db.finalize_purchase_transaction(txn_id, sub_uuid, sub_link, final_name)

        svc = db.get_service_by_uuid(sub_uuid)
        if svc:
            await us_h.send_service_details(
                context=context,
                chat_id=user_id,
                service_id=svc['service_id'],
                minimal=True
            )
        else:
            await update.message.reply_text("خرید انجام شد، اما نمایش سرویس با خطا مواجه شد. از «📋 سرویس‌های من» وارد شوید.")

    except Exception as e:
        logger.error("Purchase failed for user %s plan %s: %s", user_id, plan_id, e, exc_info=True)
        db.cancel_purchase_transaction(txn_id)
        await update.message.reply_text("❌ خطا در ایجاد سرویس. لطفاً بعداً دوباره تلاش کنید یا به پشتیبانی اطلاع دهید.")

    context.user_data.clear()
    return ConversationHandler.END