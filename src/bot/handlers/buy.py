# -*- coding: utf-8 -*-

import logging
import random
import inspect
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Message
from telegram.error import BadRequest

import database as db
import hiddify_api
from config import SUB_DOMAINS, PANEL_DOMAIN, SUB_PATH, ADMIN_PATH
from bot.constants import GET_CUSTOM_NAME, CMD_CANCEL, CMD_SKIP
from bot.handlers import user_services as us_h

logger = logging.getLogger(__name__)

# ===== Helpers =====
def _build_default_sub_link(sub_uuid: str, config_name: str) -> str:
    default_link_type = db.get_setting('default_sub_link_type') or 'sub'
    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    base_link = f"https://{sub_domain}/{sub_path}/{sub_uuid}"
    return f"{base_link}/{default_link_type}/?name={config_name.replace(' ', '_')}"

async def _create_user_subscription_compat(user_id: int, name: str, days: int, gb: int) -> dict | None:
    """
    تلاش برای ساخت سرویس در پنل با توابع متداول hiddify_api.
    خروجی نرمالایز شده: {'sub_uuid': '...'} یا None
    """
    candidates = []

    # 1) create_hiddify_user(days, gb, user_id, custom_name=...)
    if hasattr(hiddify_api, "create_hiddify_user"):
        async def call_create_hiddify_user():
            return await hiddify_api.create_hiddify_user(days, gb, user_id, custom_name=name)
        candidates.append(("create_hiddify_user", call_create_hiddify_user))

    # 2) create_user_subscription(name=..., days=..., gb=...)
    if hasattr(hiddify_api, "create_user_subscription"):
        async def call_cus_kw():
            return await hiddify_api.create_user_subscription(name=name, days=days, gb=gb)
        candidates.append(("create_user_subscription_kw", call_cus_kw))

        async def call_cus_pos():
            return await hiddify_api.create_user_subscription(days, gb, name)
        candidates.append(("create_user_subscription_pos", call_cus_pos))

    # 3) create_user(...)
    if hasattr(hiddify_api, "create_user"):
        async def call_cu_kw():
            return await hiddify_api.create_user(name=name, days=days, gb=gb)
        candidates.append(("create_user_kw", call_cu_kw))

        async def call_cu_pos():
            return await hiddify_api.create_user(days, gb, name)
        candidates.append(("create_user_pos", call_cu_pos))

    # 4) provision_user_subscription(...)
    if hasattr(hiddify_api, "provision_user_subscription"):
        async def call_prov():
            return await hiddify_api.provision_user_subscription(name=name, days=days, gb=gb)
        candidates.append(("provision_user_subscription", call_prov))

    for tag, fn in candidates:
        try:
            result = await fn()
            if isinstance(result, dict):
                if result.get("sub_uuid"):
                    return {"sub_uuid": result["sub_uuid"]}
                if result.get("uuid"):
                    return {"sub_uuid": result["uuid"]}
            if isinstance(result, str) and len(result) >= 8:
                return {"sub_uuid": result}
        except Exception as e:
            logger.debug("Provision attempt %s failed: %s", tag, e)
            continue

    return None

# ===== Public handlers =====
async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    return await _process_purchase(update, context, custom_name=name)

async def skip_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _process_purchase(update, context, custom_name="سرویس من")

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

        provision = await _create_user_subscription_compat(user_id, custom_name, plan['days'], plan['gb'])
        if not provision or not provision.get("sub_uuid"):
            raise RuntimeError("Provisioning failed or no sub_uuid returned.")

        sub_uuid = provision["sub_uuid"]
        sub_link = _build_default_sub_link(sub_uuid, custom_name)

        db.finalize_purchase_transaction(txn_id, sub_uuid, sub_link, custom_name)

        svc = db.get_service_by_uuid(sub_uuid)
        if svc:
            await us_h.send_service_details(
                context=context,
                chat_id=user_id,
                service_id=svc['service_id'],
                original_message=None,
                is_from_menu=False,
                minimal=True  # فقط دو دکمه
            )
        else:
            await update.message.reply_text("خرید انجام شد، اما نمایش سرویس با خطا مواجه شد. از «📋 سرویس‌های من» وارد شوید.")

    except Exception as e:
        logger.error("Purchase failed for user %s plan %s: %s", user_id, plan_id, e, exc_info=True)
        db.cancel_purchase_transaction(txn_id)
        await update.message.reply_text("❌ خطا در ایجاد سرویس. لطفاً بعداً دوباره تلاش کنید یا به پشتیبانی اطلاع دهید.")

    context.user_data.clear()
    return ConversationHandler.END