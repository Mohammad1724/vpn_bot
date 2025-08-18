# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes
from telegram import Update, ReplyKeyboardMarkup
from bot.constants import REPORTS_MENU, BTN_BACK_TO_ADMIN_MENU
import database as db
from config import ADMIN_ID

logger = logging.getLogger(__name__)


def _reports_menu_keyboard():
    keyboard = [
        ["📊 آمار کلی", "📈 گزارش فروش امروز"],
        ["📅 گزارش فروش ۷ روز اخیر", "🏆 محبوب‌ترین پلن‌ها"],
        [BTN_BACK_TO_ADMIN_MENU]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ممکن است با Message یا CallbackQuery صدا زده شود
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
    await update.effective_message.reply_text(
        "بخش گزارش‌ها و آمار",
        reply_markup=_reports_menu_keyboard()
    )
    return REPORTS_MENU


async def show_stats_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()

    stats = db.get_stats()
    text = (
        f"📊 **آمار کلی ربات**\n\n"
        f"👥 تعداد کاربران: {stats.get('total_users', 0)}\n"
        f"✅ سرویس‌های فعال: {stats.get('active_services', 0)}\n"
        f"💰 مجموع فروش: {stats.get('total_revenue', 0):,.0f} تومان\n"
        f"🚫 کاربران مسدود: {stats.get('banned_users', 0)}"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")
    return REPORTS_MENU


async def show_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()

    sales = db.get_sales_report(days=1)
    total_revenue = sum(s['price'] for s in sales if s['price'])
    await update.effective_message.reply_text(
        f"📈 **گزارش فروش امروز**\n\nتعداد فروش: {len(sales)}\nمجموع درآمد: {total_revenue:,.0f} تومان",
        parse_mode="Markdown"
    )
    return REPORTS_MENU


async def show_weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()

    sales = db.get_sales_report(days=7)
    total_revenue = sum(s['price'] for s in sales if s['price'])
    await update.effective_message.reply_text(
        f"📅 **گزارش فروش ۷ روز اخیر**\n\nتعداد فروش: {len(sales)}\nمجموع درآمد: {total_revenue:,.0f} تومان",
        parse_mode="Markdown"
    )
    return REPORTS_MENU


async def show_popular_plans_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()

    plans = db.get_popular_plans(limit=5)
    if not plans:
        await update.effective_message.reply_text("هنوز هیچ پلنی فروخته نشده است.")
    else:
        text = "🏆 **محبوب‌ترین پلن‌ها**\n\n" + "\n".join(
            [f"{i}. **{plan['name']}** - {plan['sales_count']} فروش" for i, plan in enumerate(plans, 1)]
        )
        await update.effective_message.reply_text(text, parse_mode="Markdown")
    return REPORTS_MENU


# --- Scheduled Report Functions ---
async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: sending daily summary to admin...")
    sales_today = db.get_sales_report(days=1)
    revenue_today = sum(s['price'] for s in sales_today if s['price'])
    new_users_today = db.get_new_users_count(days=1)

    text = (
        f"📊 **خلاصه گزارش روزانه**\n\n"
        f"👥 کاربران جدید امروز: **{new_users_today}** نفر\n"
        f"🛍️ تعداد فروش امروز: **{len(sales_today)}** عدد\n"
        f"💰 درآمد امروز: **{revenue_today:,.0f}** تومان"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send daily summary: {e}")


async def send_weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: sending weekly summary to admin...")
    sales_week = db.get_sales_report(days=7)
    revenue_week = sum(s['price'] for s in sales_week if s['price'])
    new_users_week = db.get_new_users_count(days=7)

    text = (
        f"📅 **خلاصه گزارش هفتگی**\n\n"
        f"👥 کاربران جدید در ۷ روز اخیر: **{new_users_week}** نفر\n"
        f"🛍️ تعداد فروش در ۷ روز اخیر: **{len(sales_week)}** عدد\n"
        f"💰 درآمد در ۷ روز اخیر: **{revenue_week:,.0f}** تومان"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send weekly summary: {e}")