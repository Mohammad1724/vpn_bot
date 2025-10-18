# filename: bot/handlers/admin/reports.py
# -*- coding: utf-8 -*-

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)

# ---------- Inline Keyboards ----------
def _reports_menu_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 آمار کلی", callback_data="rep_stats"),
            InlineKeyboardButton("📈 فروش امروز", callback_data="rep_daily"),
        ],
        [
            InlineKeyboardButton("📅 فروش ۷ روز اخیر", callback_data="rep_weekly"),
            InlineKeyboardButton("🏆 محبوب‌ترین پلن‌ها", callback_data="rep_popular"),
        ],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

def _back_to_reports_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به گزارش‌ها", callback_data="rep_menu")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

# ---------- Views ----------
async def reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    text = "بخش گزارش‌ها و آمار"
    kb = _reports_menu_inline_kb()
    if q:
        await q.answer()
        try:
            await q.edit_message_text(text, reply_markup=kb)
        except Exception:
            await q.message.reply_text(text, reply_markup=kb)
    else:
        await update.effective_message.reply_text(text, reply_markup=kb)
    return REPORTS_MENU

async def show_stats_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
    stats = db.get_stats()
    text = (
        "📊 آمار کلی ربات\n\n"
        f"👥 تعداد کاربران: {stats.get('total_users', 0):,}\n"
        f"✅ سرویس‌های فعال: {stats.get('active_services', 0):,}\n"
        f"💰 مجموع فروش: {float(stats.get('total_revenue', 0.0)):,.0f} تومان\n"
        f"🚫 کاربران مسدود: {stats.get('banned_users', 0):,}"
    )
    kb = _back_to_reports_kb()
    try:
        if q:
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return REPORTS_MENU

async def show_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
    sales = db.get_sales_report(days=1) or []
    total_revenue = sum(float(s.get('price') or 0) for s in sales)
    text = (
        "📈 گزارش فروش امروز\n\n"
        f"🧾 تعداد فروش: {len(sales):,}\n"
        f"💰 مجموع درآمد: {total_revenue:,.0f} تومان"
    )
    kb = _back_to_reports_kb()
    try:
        if q:
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return REPORTS_MENU

async def show_weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
    sales = db.get_sales_report(days=7) or []
    total_revenue = sum(float(s.get('price') or 0) for s in sales)
    text = (
        "📅 گزارش فروش ۷ روز اخیر\n\n"
        f"🧾 تعداد فروش: {len(sales):,}\n"
        f"💰 مجموع درآمد: {total_revenue:,.0f} تومان"
    )
    kb = _back_to_reports_kb()
    try:
        if q:
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return REPORTS_MENU

async def show_popular_plans_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
    plans = db.get_popular_plans(limit=5) or []
    if not plans:
        text = "🏆 محبوب‌ترین پلن‌ها\n\nهنوز هیچ پلنی فروخته نشده است."
    else:
        lines = []
        for i, plan in enumerate(plans, 1):
            name = plan.get('name') or '-'
            sales_count = int(plan.get('sales_count') or 0)
            lines.append(f"{i}. {name} — {sales_count:,} فروش")
        text = "🏆 محبوب‌ترین پلن‌ها\n\n" + "\n".join(lines)
    kb = _back_to_reports_kb()
    try:
        if q:
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return REPORTS_MENU

# --- Scheduled Report Functions (unchanged) ---
async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: sending daily summary to admin...")
    sales_today = db.get_sales_report(days=1) or []
    revenue_today = sum(float(s.get('price') or 0) for s in sales_today)
    new_users_today = db.get_new_users_count(days=1)
    text = (
        "📊 خلاصه گزارش روزانه\n\n"
        f"👥 کاربران جدید امروز: {new_users_today:,}\n"
        f"🛍️ تعداد فروش امروز: {len(sales_today):,}\n"
        f"💰 درآمد امروز: {revenue_today:,.0f} تومان"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Failed to send daily summary: {e}")

async def send_weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: sending weekly summary to admin...")
    sales_week = db.get_sales_report(days=7) or []
    revenue_week = sum(float(s.get('price') or 0) for s in sales_week)
    new_users_week = db.get_new_users_count(days=7)
    text = (
        "📅 خلاصه گزارش هفتگی\n\n"
        f"👥 کاربران جدید در ۷ روز اخیر: {new_users_week:,}\n"
        f"🛍️ تعداد فروش در ۷ روز اخیر: {len(sales_week):,}\n"
        f"💰 درآمد در ۷ روز اخیر: {revenue_week:,.0f} تومان"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Failed to send weekly summary: {e}")

async def miniapp_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    زیرمنو ویرایش پورت و ساب‌دامین مخصوص Mini App داخل منوی «گزارش‌ها و آمار».
    از فلو عمومی تنظیمات استفاده می‌کند: admin_settings.edit_setting_start
    """
    q = update.callback_query
    if q:
        await q.answer()

    # مقادیر فعلی
    port = db.get_setting("mini_app_port") or "—"
    subd = db.get_setting("mini_app_subdomain") or "—"

    text = (
        "⚙️ تنظیمات مینی‌اپ (پورت و ساب‌دامین)\n\n"
        f"• پورت فعلی: {port}\n"
        f"• ساب‌دامین فعلی: {subd}\n\n"
        "با دکمه‌های زیر مقدار جدید را وارد کنید."
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛠️ ویرایش پورت", callback_data="admin_edit_setting_mini_app_port"),
            InlineKeyboardButton("🌐 ویرایش ساب‌دامین", callback_data="admin_edit_setting_mini_app_subdomain"),
        ],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="rep_menu")],
    ])

    try:
        if q and q.message:
            await q.message.edit_text(text, reply_markup=kb)
        else:
            await context.bot.send_message(chat_id=update.effective_user.id, text=text, reply_markup=kb)
    except BadRequest:
        await context.bot.send_message(chat_id=update.effective_user.id, text=text, reply_markup=kb)
