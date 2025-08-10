# -*- coding: utf-8 -*-

import logging
import random
import inspect
from telegram.ext import ContextTypes
from telegram import Update
from telegram.error import BadRequest

import database as db
import hiddify_api
from config import TRIAL_ENABLED, TRIAL_DAYS, TRIAL_GB, SUB_DOMAINS, PANEL_DOMAIN, SUB_PATH, ADMIN_PATH
from .user_services import send_service_details

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
    تلاش برای ثبت Note روی کاربر/سرویس در پنل بعد از ساخت.
    با چند امضا/نام رایج امتحان می‌کنیم تا با نسخه‌های مختلف hiddify_api سازگار باشد.
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
    logger.debug("No set_note endpoint matched; skipped setting note on panel.")

async def _create_user_subscription_compat(user_id: int, name: str, days: int, gb: int, note: str | None = None) -> dict | None:
    """
    ساخت سرویس در پنل با سازگاری امضاها. اگر پارامتر note پشتیبانی نشود،
    بعد از ساخت با _set_user_note_compat تنظیم می‌کنیم.
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

# ===== Entry point for trial =====
async def get_trial_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username

    # فعال بودن سرویس تست
    if not TRIAL_ENABLED:
        await update.message.reply_text("🧪 سرویس تست در حال حاضر فعال نیست.")
        return

    # فقط یک بار مجاز
    info = db.get_or_create_user(user_id, user.username or "")
    if info and info.get("has_used_trial"):
        await update.message.reply_text("🧪 شما قبلاً از سرویس تست استفاده کرده‌اید.")
        return

    name = f"سرویس تست ({TRIAL_GB}GB/{TRIAL_DAYS}d)"
    loading = await update.message.reply_text("⏳ در حال ایجاد سرویس تست شما...")

    try:
        note = _build_note_for_user(user_id, username)
        provision = await _create_user_subscription_compat(user_id, name, TRIAL_DAYS, TRIAL_GB, note=note)
        if not provision or not provision.get("sub_uuid"):
            raise RuntimeError("Provisioning failed or no sub_uuid returned.")

        sub_uuid = provision["sub_uuid"]
        sub_link = _build_default_sub_link(sub_uuid, name)

        # ثبت در DB
        db.add_active_service(user_id, name, sub_uuid, sub_link, plan_id=None)
        db.set_user_trial_used(user_id)

        svc = db.get_service_by_uuid(sub_uuid)
        try:
            await loading.delete()
        except BadRequest:
            pass

        if svc:
            # نمایش کارت مینیمال: فقط «لینک پیش‌فرض» + «🧩 سایر لینک‌ها»
            await send_service_details(
                context=context,
                chat_id=user_id,
                service_id=svc['service_id'],
                original_message=None,
                is_from_menu=False,
                minimal=True
            )
        else:
            await update.message.reply_text("✅ سرویس تست ساخته شد، اما نمایش لینک با خطا مواجه شد. از «📋 سرویس‌های من» استفاده کنید.")

    except Exception as e:
        logger.error("Trial provision failed for user %s: %s", user_id, e, exc_info=True)
        try:
            await loading.edit_text("❌ ساخت سرویس تست ناموفق بود. لطفاً بعداً تلاش کنید.")
        except BadRequest:
            await update.message.reply_text("❌ ساخت سرویس تست ناموفق بود. لطفاً بعداً تلاش کنید.")