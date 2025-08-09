# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes
from telegram import Update
import database as db
import hiddify_api
from config import TRIAL_ENABLED, TRIAL_DAYS, TRIAL_GB
from .user_services import show_link_options_menu

async def get_trial_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = db.get_or_create_user(user_id, update.effective_user.username)
    if not TRIAL_ENABLED:
        await update.message.reply_text("سرویس تست رایگان در حال حاضر غیرفعال است.")
        return
    if user_info.get('has_used_trial'):
        await update.message.reply_text("شما قبلاً از سرویس تست رایگان استفاده کرده‌اید.")
        return
    msg_loading = await update.message.reply_text("در حال ساخت سرویس تست... ⏳")
    result = await hiddify_api.create_hiddify_user(TRIAL_DAYS, TRIAL_GB, user_id, custom_name="سرویس تست")
    if result and result.get('uuid'):
        db.set_user_trial_used(user_id)
        db.add_active_service(user_id, "سرویس تست", result['uuid'], result['full_link'], 0)
        await show_link_options_menu(update.message, result['uuid'], is_edit=False)
    else:
        await msg_loading.edit_text("❌ ساخت سرویس تست با خطا مواجه شد. لطفاً بعداً تلاش کنید.")