# -*- coding: utf-8 -*-

import logging
import uuid
from telegram.ext import ContextTypes
from telegram import Update
from telegram.error import BadRequest

import database as db
import hiddify_api
from config import TRIAL_ENABLED, TRIAL_DAYS, TRIAL_GB
from .user_services import send_service_details

logger = logging.getLogger(__name__)

# ===== Helpers =====
def _maint_on() -> bool:
    val = db.get_setting("maintenance_enabled")
    return str(val).lower() in ("1", "true", "on", "yes")

def _maint_msg() -> str:
    return db.get_setting("maintenance_message") or "⛔️ ربات در حال بروزرسانی است. لطفاً کمی بعد مراجعه کنید."

def _build_note_for_user(user_id: int, username: str | None) -> str:
    if username:
        u = username.lstrip('@')
        return f"tg:@{u}|id:{user_id}"
    return f"tg:id:{user_id}"

# ===== Entry point for trial =====
async def get_trial_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username

    if _maint_on():
        await update.message.reply_text(_maint_msg())
        return

    if not TRIAL_ENABLED:
        await update.message.reply_text("🧪 سرویس تست در حال حاضر فعال نیست.")
        return

    info = db.get_or_create_user(user_id, user.username or "")
    if info and info.get("has_used_trial"):
        await update.message.reply_text("🧪 شما قبلاً از سرویس تست استفاده کرده‌اید.")
        return

    name = "سرویس تست"
    loading = await update.message.reply_text("⏳ در حال ایجاد سرویس تست شما...")

    try:
        note = _build_note_for_user(user_id, username)

        provision = await hiddify_api.create_hiddify_user(
            plan_days=TRIAL_DAYS,
            plan_gb=TRIAL_GB,
            user_telegram_id=note,
            custom_name=name
        )
        if not provision or not provision.get("uuid"):
            raise RuntimeError("Provisioning failed or no uuid returned.")

        sub_uuid = provision["uuid"]
        sub_link = provision.get('full_link', '')

        db.add_active_service(user_id, name, sub_uuid, sub_link, plan_id=None)
        db.set_user_trial_used(user_id)

        svc = db.get_service_by_uuid(sub_uuid)
        try:
            await loading.delete()
        except BadRequest:
            pass

        if svc:
            await send_service_details(
                context=context,
                chat_id=user_id,
                service_id=svc['service_id'],
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