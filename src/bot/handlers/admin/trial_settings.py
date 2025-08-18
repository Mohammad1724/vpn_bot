# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes
from telegram import Update
import database as db
from config import ADMIN_ID

logger = logging.getLogger(__name__)

async def set_trial_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("استفاده: /set_trial_days <روز>\nمثال: /set_trial_days 1")
        return
    try:
        days = int(float(args[0]))
        if days <= 0 or days > 365:
            raise ValueError()
    except Exception:
        await update.message.reply_text("❌ مقدار نامعتبر. یک عدد بین 1 تا 365 وارد کنید.")
        return
    db.set_setting("trial_days", str(days))
    await update.message.reply_text(f"✅ مدت سرویس تست روی {days} روز تنظیم شد.")

async def set_trial_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("استفاده: /set_trial_gb <حجم-گیگ>\nمثال: /set_trial_gb 0.5")
        return
    try:
        gb = float(args[0])
        if gb <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("❌ مقدار نامعتبر. یک عدد مثبت (اعشاری مجاز) وارد کنید. مثل 0.5")
        return
    # به صورت رشته ذخیره می‌کنیم تا دقت اعشاری حفظ شود
    db.set_setting("trial_gb", str(gb))
    await update.message.reply_text(f"✅ حجم سرویس تست روی {gb} گیگابایت تنظیم شد.")