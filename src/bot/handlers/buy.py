# -*- coding: utf-8 -*-

import logging
import random
import inspect
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

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

def _build_note_for_user(user_id: int, username: str | None) -> str:
    if username:
        u = username.lstrip('@')
        return f"tg:@{u} id:{user_id}"
    return f"tg:id:{user_id}"

async def _set_user_note_compat(sub_uuid: str, note: str):
    """
    بعد از ساخت، تلاش برای ثبت Note روی کاربر/سرویس در پنل (سازگار با چند امضا).
    """
    candidates = [
        ("set_user_note", dict(uuid=sub_uuid, note=note), None),
        ("set_user_note", None, (sub_uuid, note)),
        ("update_user_note", None, (sub_uuid, note)),
        ("update_user", dict(uuid=sub_uuid, note=note), None),
        ("edit_user", dict(uuid=sub_uuid, note=note), None),
        ("edit_user", None, (sub_uuid, note)),
        ("update_user_subscription", dict(uuid=sub_uuid, note=note), None),
    ]
    for func, kwargs, pos in candidates:
        try:
            if not hasattr(hiddify_api, func):
                continue
            fn = getattr(hiddify_api, func)
            res = await (fn(**kwargs) if kwargs is not None else fn(*pos))
            return
        except Exception as e:
            logger.debug("set note compat %s failed: %s", func, e)
            continue
    logger.debug("No compatible set_note endpoint found; skipped setting note.")

async def _create_user_subscription_compat(user_id: int, name: str, days: int, gb: int, note: str | None = None) -> dict | None:
    """
    ساخت سرویس در پنل با سازگاری نام/امضا.
    اگر ساخت از note پشتیبانی نکند، بعد از ساخت Note را ست می‌کنیم.
    خروجی نرمالایز: {'sub_uuid': '...'}
    """
    # 1) create_hiddify_user(days, gb, user_id, custom_name=..., [note/description/comment])
    if hasattr(hiddify_api, "create_hiddify_user"):
        fn = hiddify_api.create_hiddify_user
        sig = inspect.signature(fn)
        kwargs = {"custom_name": name}
        injected = False
        for alt in ("note", "description", "comment"):
            if alt in sig.parameters and note:
                kwargs[alt] = note
                injected = True
                break
        try:
            res = await fn(days, gb, user_id, **kwargs)
            if isinstance(res, dict):
                sub_uuid = res.get("sub_uuid") or res.get("uuid")
                if sub_uuid:
                    if note and not injected:
                        await _set_user_note_compat(sub_uuid, note)
                    return {"sub_uuid": sub_uuid}
        except Exception as e:
            logger.debug("create_hiddify_user failed: %s", e)

    # 2) سایر نام‌ها/امضاها
    for func_name, kwargs, pos in [
        ("create_user_subscription", dict(name=name, days=days, gb=gb), None),
        ("create_user_subscription", dict(), (days, gb, name)),
        ("create_user", dict(name=name, days=days, gb=gb), None),
        ("create_user", dict(), (days, gb, name)),
        ("provision_user_subscription", dict(name=name, days=days, gb=gb), None),
    ]:
        if not hasattr(hiddify_api, func_name):
            continue
        try:
            fn = getattr(hiddify_api, func_name)
            injected = False
            if note:
                sig = inspect.signature(fn)
                for alt in ("note", "description", "comment"):
                    if alt in sig.parameters:
                        kwargs[alt] = note
                        injected = True
                        break
            res = await (fn(**kwargs) if not pos else fn(*pos))
            if isinstance(res, dict):
                sub_uuid = res.get("sub_uuid") or res.get("uuid")
                if sub_uuid:
                    if note and not injected:
                        await _set_user_note_compat(sub_uuid, note)
                    return {"sub_uuid": sub_uuid}
            if isinstance(res, str) and len(res) >= 8:
                if note and not injected:
                    await _set_user_note_compat(res, note)
                return {"sub_uuid": res}
        except Exception as e:
            logger.debug("%s failed: %s", func_name, e)
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
    username = update.effective_user.username
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

        note = _build_note_for_user(user_id, username)
        provision = await _create_user_subscription_compat(user_id, custom_name, plan['days'], plan['gb'], note=note)
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
                minimal=True  # فقط دو دکمه: لینک پیش‌فرض + سایر لینک‌ها
            )
        else:
            await update.message.reply_text("خرید انجام شد، اما نمایش سرویس با خطا مواجه شد. از «📋 سرویس‌های من» وارد شوید.")

    except Exception as e:
        logger.error("Purchase failed for user %s plan %s: %s", user_id, plan_id, e, exc_info=True)
        db.cancel_purchase_transaction(txn_id)
        await update.message.reply_text("❌ خطا در ایجاد سرویس. لطفاً بعداً دوباره تلاش کنید یا به پشتیبانی اطلاع دهید.")

    context.user_data.clear()
    return ConversationHandler.END