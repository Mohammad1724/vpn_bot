# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest
from telegram.constants import ParseMode

import database as db
import hiddify_api
from bot import utils

logger = logging.getLogger(__name__)

def _maint_on(): return str(db.get_setting("maintenance_enabled")).lower() in ("1", "true", "on", "yes")
def _maint_msg(): return db.get_setting("maintenance_message") or "⛔️ ربات در حال بروزرسانی است. لطفاً کمی بعد مراجعه کنید."
def _build_note_for_user(user_id: int, username: str | None): return f"tg:@{username.lstrip('@')}|id:{user_id}" if username else f"tg:id:{user_id}"

async def get_trial_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    user = update.effective_user
    user_id = user.id
    username = user.username

    if _maint_on():
        await em.reply_text(_maint_msg())
        return

    info = db.get_or_create_user(user_id, user.username or "")
    if info and info.get("has_used_trial"):
        await em.reply_text("🧪 شما قبلاً از سرویس تست استفاده کرده‌اید.")
        return

    raw_days = str(db.get_setting("trial_days") or "1").strip().replace(",", ".")
    raw_gb = str(db.get_setting("trial_gb") or "1").strip().replace(",", ".")
    try:
        trial_days = max(1, int(float(raw_days)))
    except Exception:
        trial_days = 1
    try:
        trial_gb = float(raw_gb)
        if trial_gb <= 0:
            raise ValueError()
    except Exception:
        trial_gb = 1.0

    name = "سرویس تست"
    loading_message = await em.reply_text("⏳ در حال ایجاد سرویس تست شما...")

    try:
        note = _build_note_for_user(user_id, username)

        provision = await hiddify_api.create_hiddify_user(
            plan_days=trial_days,
            plan_gb=trial_gb,
            user_telegram_id=note,
            custom_name=name
        )
        if not provision or not provision.get("uuid"):
            raise RuntimeError("Provisioning for trial failed or no uuid returned.")

        new_uuid = provision["uuid"]
        sub_link = provision.get('full_link', '')

        db.add_active_service(user_id, name, new_uuid, sub_link, plan_id=None)
        db.set_user_trial_used(user_id)

        try:
            await loading_message.delete()
        except BadRequest:
            pass

        new_service_record = db.get_service_by_uuid(new_uuid)

        user_data = await hiddify_api.get_user_info(new_uuid)
        if user_data:
            sub_url = utils.build_subscription_url(new_uuid)
            qr_bio = utils.make_qr_bytes(sub_url)
            caption = utils.create_service_info_caption(
                user_data,
                service_db_record=new_service_record,
                title="🎉 سرویس تست شما با موفقیت ساخته شد!"
            )

            inline_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📚 راهنمای اتصال", callback_data="guide_connection"),
                    InlineKeyboardButton("📋 سرویس‌های من", callback_data="back_to_services")
                ]
            ])

            await context.bot.send_photo(
                chat_id=user_id,
                photo=InputFile(qr_bio),
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=inline_kb
            )

            from bot.keyboards import get_main_menu_keyboard
            await context.bot.send_message(
                chat_id=user_id,
                text="منوی اصلی:",
                reply_markup=get_main_menu_keyboard(user_id)
            )
        else:
            from bot.keyboards import get_main_menu_keyboard
            await em.reply_text(
                "✅ سرویس تست ساخته شد، اما دریافت اطلاعات سرویس با خطا مواجه شد. از «📋 سرویس‌های من» استفاده کنید.",
                reply_markup=get_main_menu_keyboard(user_id)
            )
    except Exception as e:
        logger.error("Trial provision failed for user %s: %s", user_id, e, exc_info=True)
        try:
            await loading_message.edit_text("❌ ساخت سرویس تست ناموفق بود. لطفاً بعداً تلاش کنید.")
        except BadRequest:
            await em.reply_text("❌ ساخت سرویس تست ناموفق بود. لطفاً بعداً تلاش کنید.")