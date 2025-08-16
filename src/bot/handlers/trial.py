# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes
from telegram import Update
from telegram.error import BadRequest
from telegram.constants import ParseMode

import database as db
import hiddify_api
from config import TRIAL_ENABLED, TRIAL_DAYS, TRIAL_GB
from bot import utils
from bot.handlers.start import get_main_keyboard

logger = logging.getLogger(__name__)

def _maint_on(): return str(db.get_setting("maintenance_enabled")).lower() in ("1", "true", "on", "yes")
def _maint_msg(): return db.get_setting("maintenance_message") or "⛔️ ربات در حال بروزرسانی است. لطفاً کمی بعد مراجعه کنید."
def _build_note_for_user(user_id: int, username: str | None): return f"tg:@{username.lstrip('@')}|id:{user_id}" if username else f"tg:id:{user_id}"

async def get_trial_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; user_id = user.id; username = user.username
    if _maint_on(): await update.message.reply_text(_maint_msg()); return
    if not TRIAL_ENABLED: await update.message.reply_text("🧪 سرویس تست در حال حاضر فعال نیست."); return
    info = db.get_or_create_user(user_id, user.username or "")
    if info and info.get("has_used_trial"): await update.message.reply_text("🧪 شما قبلاً از سرویس تست استفاده کرده‌اید."); return
    name = "سرویس تست"; loading_message = await update.message.reply_text("⏳ در حال ایجاد سرویس تست شما...")
    try:
        note = _build_note_for_user(user_id, username)
        provision = await hiddify_api.create_hiddify_user(plan_days=TRIAL_DAYS, plan_gb=TRIAL_GB, user_telegram_id=note, custom_name=name)
        if not provision or not provision.get("uuid"): raise RuntimeError("Provisioning for trial failed or no uuid returned.")
        new_uuid = provision["uuid"]
        db.add_active_service(user_id, name, new_uuid, plan_id=None); db.set_user_trial_used(user_id)
        try: await loading_message.delete()
        except BadRequest: pass
        user_data = await hiddify_api.get_user_info(new_uuid)
        if user_data:
            message_title = "🎉 سرویس تست شما با موفقیت ساخته شد!"
            message_text = utils.create_service_info_message(user_data, title=message_title)
            await context.bot.send_message(chat_id=user_id, text=message_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user_id))
        else:
            await update.message.reply_text("✅ سرویس تست شما با موفقیت ساخته شد، اما در دریافت اطلاعات سرویس مشکلی پیش آمد. لطفاً از منوی «سرویس‌های من» آن را مشاهده کنید.", reply_markup=get_main_keyboard(user_id))
    except Exception as e:
        logger.error("Trial provision failed for user %s: %s", user_id, e, exc_info=True)
        try: await loading_message.edit_text("❌ ساخت سرویس تست ناموفق بود. لطفاً بعداً تلاش کنید.")
        except BadRequest: await update.message.reply_text("❌ ساخت سرویس تست ناموفق بود. لطفاً بعداً تلاش کنید.")