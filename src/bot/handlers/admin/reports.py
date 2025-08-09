# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes
from telegram import Update
import database as db

async def reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📊 آمار کلی", "📈 گزارش‌ها و آمار"], ["📅 گزارش فروش ۷ روز اخیر", "🏆 محبوب‌ترین پلن‌ها"], ["بازگشت به منوی ادمین"]]
    from telegram import ReplyKeyboardMarkup
    await update.message.reply_text("بخش گزارش‌ها و آمار", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def show_stats_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_stats()
    text = (
        f"📊 آمار کلی ربات\n\n"
        f"👥 تعداد کاربران: {stats.get('total_users', 0)}\n"
        f"✅ سرویس‌های فعال: {stats.get('active_services', 0)}\n"
        f"💰 مجموع فروش: {stats.get('total_revenue', 0):,.0f} تومان\n"
        f"🚫 کاربران مسدود: {stats.get('banned_users', 0)}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def show_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sales = db.get_sales_report(days=1)
    total_revenue = sum(s['price'] for s in sales if s['price'])
    await update.message.reply_text(
        f"📈 گزارش فروش امروز\n\nتعداد فروش: {len(sales)}\nمجموع درآمد: {total_revenue:,.0f} تومان",
        parse_mode="Markdown"
    )

async def show_weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sales = db.get_sales_report(days=7)
    total_revenue = sum(s['price'] for s in sales if s['price'])
    await update.message.reply_text(
        f"📅 گزارش فروش ۷ روز اخیر\n\nتعداد فروش: {len(sales)}\nمجموع درآمد: {total_revenue:,.0f} تومان",
        parse_mode="Markdown"
    )

async def show_popular_plans_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.get_popular_plans(limit=5)
    if not plans:
        await update.message.reply_text("هنوز هیچ پلنی فروخته نشده است.")
        return
    text = "🏆 محبوب‌ترین پلن‌ها\n\n" + "\n".join(
        [f"{i}. **{plan['name']}** - {plan['sales_count']} فروش" for i, plan in enumerate(plans, 1)]
    )
    await update.message.reply_text(text, parse_mode="Markdown")