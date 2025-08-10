# -*- coding: utf-8 -*-

import logging
import random
import inspect
import httpx
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

import database as db
import hiddify_api
from config import SUB_DOMAINS, PANEL_DOMAIN, SUB_PATH, ADMIN_PATH, API_KEY
from bot.constants import GET_CUSTOM_NAME, CMD_CANCEL, CMD_SKIP
from bot.handlers import user_services as us_h

logger = logging.getLogger(__name__)

# ===== Helpers =====

def _maint_on() -> bool:
    val = db.get_setting("maintenance_enabled")
    return str(val).lower() in ("1", "true", "on", "yes")

def _maint_msg() -> str:
    return db.get_setting("maintenance_message") or "⛔️ ربات در حال بروزرسانی است. لطفاً کمی بعد مراجعه کنید."

def _build_default_sub_link(sub_uuid: str, config_name: str) -> str:
    default_link_type = db.get_setting('default_sub_link_type') or 'sub'
    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    base_link = f"https://{sub_domain}/{sub_path}/{sub_uuid}"
    return f"{base_link}/{default_link_type}/?name={config_name.replace(' ', '_')}"

def _build_note_for_user(user_id: int, username: str | None) -> str:
    # اگر فقط آی‌دی می‌خواهی:
    # return f"tg_id:{user_id}"
    if username:
        u = username.lstrip('@')
        return f"tg:@{u} id:{user_id}"
    return f"tg:id:{user_id}"

async def _get_panel_user_id(sub_uuid: str) -> int | None:
    try:
        info = await hiddify_api.get_user_info(sub_uuid)
        if isinstance(info, dict):
            for k in ("id", "user_id", "uid"):
                if k in info and info[k]:
                    return int(info[k])
    except Exception as e:
        logger.debug("get_panel_user_id failed: %s", e)
    return None

async def _call_api(fn, *args, **kwargs):
    try:
        res = fn(*args, **kwargs)
        if inspect.isawaitable(res):
            await res
        return True
    except Exception as e:
        logger.debug("API call %s failed: %s", getattr(fn, '__name__', fn), e)
        return False

async def _set_user_note_http_fallback(panel_user_id: int, note: str) -> bool:
    """
    تلاش مستقیم با HTTP روی API پنل:
    - مسیرهای احتمالی: /api/v1/users/{id}, /api/users/{id}, /api/user/{id}
    - متدهای PATCH/PUT
    - هدرهای Authorization/X-API-Key
    - کلیدهای note/description/comment/telegram/telegram_id
    """
    base = f"https://{PANEL_DOMAIN}/{ADMIN_PATH}".strip().rstrip('/')
    api_base_candidates = [f"{base}/api/v1", f"{base}/api", base]  # ترتیب تست

    headers_candidates = [
        {"Authorization": f"Bearer {API_KEY}"},
        {"X-API-Key": API_KEY},
    ]
    methods = ("PATCH", "PUT")
    body_keys = ("note", "description", "comment", "telegram", "telegram_id")
    path_templates = ("/users/{id}", "/user/{id}")

    async with httpx.AsyncClient(timeout=10) as client:
        for api_base in api_base_candidates:
            for path_tpl in path_templates:
                url = f"{api_base}{path_tpl.format(id=panel_user_id)}"
                for hdr in headers_candidates:
                    for method in methods:
                        for key in body_keys:
                            data = {key: note}
                            try:
                                r = await client.request(method, url, json=data, headers=hdr, verify=True)
                                if 200 <= r.status_code < 300:
                                    logger.info("HTTP note set OK via %s %s with key=%s", method, url, key)
                                    return True
                                else:
                                    logger.debug("HTTP note attempt %s %s (%s) -> %s %s",
                                                 method, url, key, r.status_code, r.text[:200])
                            except Exception as e:
                                logger.debug("HTTP note attempt failed: %s %s (%s): %s", method, url, key, e)

    logger.warning("HTTP fallback failed to set note for panel_user_id=%s", panel_user_id)
    return False

async def _set_user_note_compat(sub_uuid: str, note: str):
    """
    بعد از ساخت، تلاش برای ثبت Note:
    - ابتدا از hiddify_api با امضاهای مختلف (uuid و id)
    - در صورت شکست، تلاش مستقیم HTTP روی پنل
    """
    panel_user_id = await _get_panel_user_id(sub_uuid)

    attempts = []

    # با uuid
    if hasattr(hiddify_api, "set_user_note"):
        attempts.append((hiddify_api.set_user_note, (), {"uuid": sub_uuid, "note": note}))
        attempts.append((hiddify_api.set_user_note, (sub_uuid, note), {}))
    if hasattr(hiddify_api, "update_user_note"):
        attempts.append((hiddify_api.update_user_note, (sub_uuid, note), {}))
    if hasattr(hiddify_api, "update_user"):
        attempts.append((hiddify_api.update_user, (), {"uuid": sub_uuid, "note": note}))
        attempts.append((hiddify_api.update_user, (), {"uuid": sub_uuid, "description": note}))
        attempts.append((hiddify_api.update_user, (), {"uuid": sub_uuid, "comment": note}))
        attempts.append((hiddify_api.update_user, (), {"uuid": sub_uuid, "telegram": note}))
        attempts.append((hiddify_api.update_user, (), {"uuid": sub_uuid, "telegram_id": note}))
    if hasattr(hiddify_api, "edit_user"):
        attempts.append((hiddify_api.edit_user, (), {"uuid": sub_uuid, "note": note}))
        attempts.append((hiddify_api.edit_user, (), {"uuid": sub_uuid, "description": note}))
        attempts.append((hiddify_api.edit_user, (), {"uuid": sub_uuid, "comment": note}))
        attempts.append((hiddify_api.edit_user, (), {"uuid": sub_uuid, "telegram": note}))
    if hasattr(hiddify_api, "update_user_subscription"):
        attempts.append((hiddify_api.update_user_subscription, (), {"uuid": sub_uuid, "note": note}))
    if hasattr(hiddify_api, "set_user_comment"):
        attempts.append((hiddify_api.set_user_comment, (), {"uuid": sub_uuid, "comment": note}))
    if hasattr(hiddify_api, "set_comment"):
        attempts.append((hiddify_api.set_comment, (), {"uuid": sub_uuid, "comment": note}))

    # با panel_user_id (اگر موجود باشد)
    if panel_user_id is not None:
        if hasattr(hiddify_api, "set_user_note"):
            attempts.append((hiddify_api.set_user_note, (), {"id": panel_user_id, "note": note}))
        if hasattr(hiddify_api, "update_user"):
            attempts.append((hiddify_api.update_user, (), {"id": panel_user_id, "note": note}))
            attempts.append((hiddify_api.update_user, (), {"id": panel_user_id, "description": note}))
            attempts.append((hiddify_api.update_user, (), {"id": panel_user_id, "comment": note}))
            attempts.append((hiddify_api.update_user, (), {"id": panel_user_id, "telegram": note}))
            attempts.append((hiddify_api.update_user, (), {"id": panel_user_id, "telegram_id": note}))
        if hasattr(hiddify_api, "edit_user"):
            attempts.append((hiddify_api.edit_user, (), {"id": panel_user_id, "note": note}))
            attempts.append((hiddify_api.edit_user, (), {"id": panel_user_id, "description": note}))
            attempts.append((hiddify_api.edit_user, (), {"id": panel_user_id, "comment": note}))
            attempts.append((hiddify_api.edit_user, (), {"id": panel_user_id, "telegram": note}))
        if hasattr(hiddify_api, "update_user_subscription"):
            attempts.append((hiddify_api.update_user_subscription, (), {"id": panel_user_id, "note": note}))
        if hasattr(hiddify_api, "set_user_comment"):
            attempts.append((hiddify_api.set_user_comment, (), {"id": panel_user_id, "comment": note}))
        if hasattr(hiddify_api, "set_comment"):
            attempts.append((hiddify_api.set_comment, (), {"id": panel_user_id, "comment": note}))

    # اجرای تلاش‌ها
    for fn, args, kwargs in attempts:
        ok = await _call_api(fn, *args, **kwargs)
        if ok:
            logger.info("Note set via %s (%s)", getattr(fn, '__name__', fn), "uuid" if "uuid" in kwargs else "id")
            return True

    # HTTP fallback (اگر panel_user_id داشتیم)
    if panel_user_id is not None:
        http_ok = await _set_user_note_http_fallback(panel_user_id, note)
        if http_ok:
            return True

    logger.warning("All note attempts failed for uuid=%s (panel_user_id=%s)", sub_uuid, panel_user_id)
    return False

async def _create_user_subscription_compat(user_id: int, name: str, days: int, gb: int, note: str | None = None) -> dict | None:
    """
    ساخت سرویس در پنل با سازگاری نام/امضا.
    اگر ساخت از note پشتیبانی نکند، بعد از ساخت Note را ست می‌کنیم.
    خروجی نرمالایز: {'sub_uuid': '...'}
    """
    # 1) create_hiddify_user(days, gb, user_id, custom_name=..., [note/description/comment/telegram/telegram_id])
    if hasattr(hiddify_api, "create_hiddify_user"):
        fn = hiddify_api.create_hiddify_user
        sig = inspect.signature(fn)
        kwargs = {"custom_name": name}
        injected_key = None
        for alt in ("note", "description", "comment", "telegram", "telegram_id"):
            if alt in sig.parameters and note:
                kwargs[alt] = note
                injected_key = alt
                break
        try:
            res = await fn(days, gb, user_id, **kwargs)
            if isinstance(res, dict):
                sub_uuid = res.get("sub_uuid") or res.get("uuid")
                if sub_uuid:
                    if note and injected_key is None:
                        await _set_user_note_compat(sub_uuid, note)
                    return {"sub_uuid": sub_uuid}
        except Exception as e:
            logger.debug("create_hiddify_user failed: %s", e)

    # 2) سایر نام‌ها/امضاها (با تزریق فیلدهای شناخته‌شده)
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
            sig = inspect.signature(fn)
            injected_key = None
            if note:
                for alt in ("note", "description", "comment", "telegram", "telegram_id"):
                    if alt in sig.parameters:
                        kwargs[alt] = note
                        injected_key = alt
                        break
            res = await (fn(**kwargs) if not pos else fn(*pos))
            if isinstance(res, dict):
                sub_uuid = res.get("sub_uuid") or res.get("uuid")
                if sub_uuid:
                    if note and injected_key is None:
                        await _set_user_note_compat(sub_uuid, note)
                    return {"sub_uuid": sub_uuid}
            if isinstance(res, str) and len(res) >= 8:
                if note and injected_key is None:
                    await _set_user_note_compat(res, note)
                return {"sub_uuid": res}
        except Exception as e:
            logger.debug("%s failed: %s", func_name, e)
            continue
    return None

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