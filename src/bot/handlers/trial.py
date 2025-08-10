# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes
from telegram import Update
from telegram.error import BadRequest

import database as db
import hiddify_api
from config import TRIAL_ENABLED, TRIAL_DAYS, TRIAL_GB
from .user_services import send_service_details

logger = logging.getLogger(__name__)

def _build_note_for_user(user_id: int, username: str | None) -> str:
    if username:
        u = username.lstrip('@')
        return f"tg:@{u}|id:{user_id}"
    return f"tg:id:{user_id}"


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

    # ساخت نام سرویس در پنل (با Note آی‌دی تلگرام)
    note = _build_note_for_user(user_id, username)
    panel_name = f"سرویس تست | {note}"

    loading = await update.message.reply_text("⏳ در حال ایجاد سرویس تست شما...")

    try:
        # device_limit=0 را پاس می‌دهیم
        provision = await hiddify_api.create_hiddify_user(
            plan_days=TRIAL_DAYS,
            plan_gb=TRIAL_GB,
            device_limit=0,
            user_telegram_id=user_id,
            custom_name=panel_name
        )
        if not provision or not provision.get("uuid"):
            raise RuntimeError("Provisioning failed or no uuid returned.")

        sub_uuid = provision["uuid"]

        # ثبت در DB ربات
        db.add_active_service(
            user_id=user_id,
            name="سرویس تست",  # نام کوتاه‌تر در ربات
            sub_uuid=sub_uuid,
            sub_link="",  # لینک بعداً ساخته می‌شود
            plan_id=None
        )
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