# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from bot.constants import (
    CMD_CANCEL, CMD_SKIP, PLAN_MENU, PLAN_NAME, PLAN_PRICE, PLAN_DAYS, PLAN_GB,
    EDIT_PLAN_NAME, EDIT_PLAN_PRICE, EDIT_PLAN_DAYS, EDIT_PLAN_GB, BTN_BACK_TO_ADMIN_MENU
)
from bot.keyboards import get_admin_menu_keyboard
import database as db

async def plan_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["➕ افزودن پلن جدید", "📋 لیست پلن‌ها"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("بخش مدیریت پلن‌ها", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return PLAN_MENU

async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans()
    if not plans:
        await update.message.reply_text("هیچ پلنی تعریف نشده است.")
        return PLAN_MENU
    await update.message.reply_text("لیست پلن‌های تعریف شده:")
    for plan in plans:
        icon = "👁️" if plan['is_visible'] else "🙈"
        text = (
            f"**{plan['name']}** (ID: {plan['plan_id']})\n"
            f"▫️ قیمت: {plan['price']:.0f} تومان\n"
            f"▫️ مدت: {plan['days']} روز\n"
            f"▫️ حجم: {plan['gb']} گیگ\n"
            f"▫️ وضعیت: {'نمایش' if plan['is_visible'] else 'مخفی'}"
        )
        kb = [[
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"admin_edit_plan_{plan['plan_id']}"),
            InlineKeyboardButton(f"{icon} تغییر وضعیت", callback_data=f"admin_toggle_plan_{plan['plan_id']}"),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"admin_delete_plan_{plan['plan_id']}")
        ]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    return PLAN_MENU

async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("نام پلن را وارد کنید:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return PLAN_NAME

async def plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['plan_name'] = update.message.text
    await update.message.reply_text("قیمت (تومان) را وارد کنید:")
    return PLAN_PRICE

async def plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_price'] = float(update.message.text)
        await update.message.reply_text("مدت (روز) را وارد کنید:")
        return PLAN_DAYS
    except ValueError:
        await update.message.reply_text("قیمت را به صورت عدد وارد کنید.")
        return PLAN_PRICE

async def plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_days'] = int(update.message.text)
        await update.message.reply_text("حجم (گیگابایت) را وارد کنید:")
        return PLAN_GB
    except ValueError:
        await update.message.reply_text("مدت را به صورت عدد وارد کنید.")
        return PLAN_DAYS

async def plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_gb'] = int(update.message.text)
        db.add_plan(context.user_data['plan_name'], context.user_data['plan_price'], context.user_data['plan_days'], context.user_data['plan_gb'])
        await update.message.reply_text("✅ پلن جدید اضافه شد!", reply_markup=get_admin_menu_keyboard())
        context.user_data.clear()
        return PLAN_MENU
    except ValueError:
        await update.message.reply_text("حجم را به صورت عدد وارد کنید.")
        return PLAN_GB

async def edit_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split('_')[-1])
    plan = db.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("پلن یافت نشد.")
        return ConversationHandler.END
    context.user_data['edit_plan_id'] = plan_id
    context.user_data['edit_plan_data'] = {}
    await query.message.reply_text(
        f"در حال ویرایش پلن: **{plan['name']}**\n\nنام جدید را وارد کنید. برای رد شدن، {CMD_SKIP} را بزنید.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup([[CMD_SKIP], [CMD_CANCEL]], resize_keyboard=True)
    )
    return EDIT_PLAN_NAME

async def edit_plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['edit_plan_data']['name'] = update.message.text
    await update.message.reply_text(f"قیمت جدید را به تومان وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_PRICE

async def skip_edit_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر نام صرف‌نظر شد. قیمت جدید را به تومان وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_PRICE

async def edit_plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['price'] = float(update.message.text)
        await update.message.reply_text(f"مدت جدید (روز) را وارد کنید (یا {CMD_SKIP}).")
        return EDIT_PLAN_DAYS
    except ValueError:
        await update.message.reply_text("قیمت را به صورت عدد وارد کنید.")
        return EDIT_PLAN_PRICE

async def skip_edit_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر قیمت صرف‌نظر شد. مدت جدید (روز) را وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_DAYS

async def edit_plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['days'] = int(update.message.text)
        await update.message.reply_text(f"حجم جدید (گیگابایت) را وارد کنید (یا {CMD_SKIP}).")
        return EDIT_PLAN_GB
    except ValueError:
        await update.message.reply_text("مدت را به صورت عدد وارد کنید.")
        return EDIT_PLAN_DAYS

async def skip_edit_plan_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر مدت صرف‌نظر شد. حجم جدید (گیگابایت) را وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_GB

async def edit_plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['gb'] = int(update.message.text)
        await finish_plan_edit(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("حجم را به صورت عدد وارد کنید.")
        return EDIT_PLAN_GB

async def skip_edit_plan_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("از تغییر حجم صرف‌نظر شد.")
    await finish_plan_edit(update, context)
    return ConversationHandler.END

async def finish_plan_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_id = context.user_data.get('edit_plan_id')
    new_data = context.user_data.get('edit_plan_data')
    if not new_data:
        await update.message.reply_text("هیچ تغییری اعمال نشد.", reply_markup=get_admin_menu_keyboard())
    else:
        db.update_plan(plan_id, new_data)
        await update.message.reply_text("✅ پلن با موفقیت به‌روزرسانی شد!", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear()
    return PLAN_MENU

async def admin_delete_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    plan_id = int(q.data.split('_')[-1])
    db.delete_plan(plan_id)
    await q.message.delete()
    await q.from_user.send_message("پلن با موفقیت حذف شد.")
    return PLAN_MENU

async def admin_toggle_plan_visibility_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    plan_id = int(q.data.split('_')[-1])
    db.toggle_plan_visibility(plan_id)
    await q.answer("وضعیت نمایش پلن تغییر کرد.")
    await q.message.delete()
    await q.from_user.send_message("وضعیت نمایش پلن تغییر کرد. برای دیدن تغییرات، لیست را مجدداً باز کنید.")
    return PLAN_MENU