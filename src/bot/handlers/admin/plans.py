# filename: bot/handlers/admin/plans.py
# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.error import BadRequest

from bot.constants import (
    CMD_CANCEL, CMD_SKIP,
    PLAN_MENU, PLAN_NAME, PLAN_PRICE, PLAN_DAYS, PLAN_GB, PLAN_CATEGORY,
    EDIT_PLAN_NAME, EDIT_PLAN_PRICE, EDIT_PLAN_DAYS, EDIT_PLAN_GB, EDIT_PLAN_CATEGORY,
)
import database as db


# ---------- Inline UI builders ----------

def _plan_menu_inline() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="admin_add_plan"),
            InlineKeyboardButton("📋 لیست پلن‌ها", callback_data="admin_list_plans"),
        ],
        [
            InlineKeyboardButton("🏠 بازگشت به منوی ادمین", callback_data="admin_panel"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def _inline_back_to_plan_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به مدیریت پلن‌ها", callback_data="admin_plans")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])


async def _send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    """
    اگر از Callback آمده باشد، پیام فعلی را ادیت می‌کند؛
    در غیر این‌صورت پیام جدید ارسال می‌کند.
    """
    q = getattr(update, "callback_query", None)
    if q:
        try:
            await q.answer()
        except Exception:
            pass
        try:
            await q.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
        except BadRequest:
            # اگر ادیت نشد (مثلاً پیام قبلی عکس بوده)، پیام جدید بفرست
            await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)


# ---------- Plan management menu ----------

async def plan_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    منوی مدیریت پلن‌ها. اگر از Callback بیاید، همون پیام ادیت می‌شود (بدون ارسال پیام جدید).
    """
    await _send_or_edit(update, context, "🧩 بخش مدیریت پلن‌ها", reply_markup=_plan_menu_inline(), parse_mode=None)
    return PLAN_MENU


async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    لیست پلن‌ها به‌صورت یک پیام واحد + کیبورد اینلاین.
    بازگشت به «مدیریت پلن‌ها» همین پیام را ادیت می‌کند.
    """
    q = getattr(update, "callback_query", None)
    if q:
        try:
            await q.answer()
        except Exception:
            pass

    plans = db.list_plans(only_visible=False)
    if not plans:
        await _send_or_edit(update, context, "هیچ پلنی تعریف نشده است.", reply_markup=_inline_back_to_plan_menu(), parse_mode=None)
        return PLAN_MENU

    # متن لیست (خوانا و بدون Markdown پیچیده)
    lines = ["📋 لیست پلن‌ها:"]
    kb_rows = []
    for p in plans:
        pid = p["plan_id"]
        visible = bool(p.get("is_visible", 1))
        vis_label = "👁️ مخفی‌کردن" if visible else "👁️‍🗨️ نمایش‌دادن"

        # متن هر پلن
        name = p.get("name") or "-"
        price = int(float(p.get("price") or 0))
        days = int(p.get("days") or 0)
        gb = int(p.get("gb") or 0)
        cat = p.get("category") or "-"
        state = "نمایش" if visible else "مخفی"
        lines.append(f"— #{pid} | {name} | {days} روز | {gb} گیگ | {price:,} تومان | {state} | دسته: {cat}")

        # ردیف کنترل هر پلن
        kb_rows.append([
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"admin_edit_plan_{pid}"),
            InlineKeyboardButton(vis_label, callback_data=f"admin_toggle_plan_{pid}"),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"admin_delete_plan_{pid}"),
        ])

    # ردیف بازگشت
    kb_rows.append([InlineKeyboardButton("🔙 بازگشت به مدیریت پلن‌ها", callback_data="admin_plans")])

    text = "\n".join(lines)
    await _send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(kb_rows), parse_mode=None)
    return PLAN_MENU


# ===== Add Plan Conversation =====
async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
    await update.effective_message.reply_text(
        "لطفاً نام پلن جدید را وارد کنید:",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
    )
    return PLAN_NAME


async def plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['plan_name'] = (update.message.text or "").strip()
    if not context.user_data['plan_name']:
        await update.message.reply_text("نام پلن نمی‌تواند خالی باشد. لطفاً دوباره وارد کنید.")
        return PLAN_NAME

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
        await update.message.reply_text("حجم (گیگابایت) را وارد کنید (برای نامحدود 0):")
        return PLAN_GB
    except ValueError:
        await update.message.reply_text("مدت را به صورت عدد وارد کنید.")
        return PLAN_DAYS


async def plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_gb'] = int(update.message.text)
        await update.message.reply_text("دسته‌بندی پلن را وارد کنید (مثلاً: یک ماهه):")
        return PLAN_CATEGORY
    except ValueError:
        await update.message.reply_text("حجم را به صورت عدد وارد کنید.")
        return PLAN_GB


async def plan_category_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['plan_category'] = (update.message.text or "").strip()

    db.add_plan(
        context.user_data['plan_name'],
        context.user_data['plan_price'],
        context.user_data['plan_days'],
        context.user_data['plan_gb'],
        context.user_data['plan_category']
    )
    await update.message.reply_text("✅ پلن جدید با موفقیت اضافه شد.", reply_markup=ReplyKeyboardRemove())
    # برگشت به منوی شیشه‌ای
    await update.message.reply_text("🧩 بخش مدیریت پلن‌ها", reply_markup=_plan_menu_inline())

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_add_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("🧩 بخش مدیریت پلن‌ها", reply_markup=_plan_menu_inline())
    return ConversationHandler.END


# ===== Edit Plan Conversation =====
async def edit_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        plan_id = int(q.data.split('_')[-1])
    except Exception:
        await q.edit_message_text("پلن یافت نشد.", reply_markup=_inline_back_to_plan_menu())
        return ConversationHandler.END

    plan = db.get_plan(plan_id)
    if not plan:
        await q.edit_message_text("پلن یافت نشد.", reply_markup=_inline_back_to_plan_menu())
        return ConversationHandler.END

    context.user_data['edit_plan_id'] = plan_id
    context.user_data['edit_plan_data'] = {}

    await q.message.reply_text(
        f"در حال ویرایش پلن: *{plan['name']}*\n\nنام جدید را وارد کنید. برای رد شدن، {CMD_SKIP} را بزنید.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup([[CMD_SKIP], [CMD_CANCEL]], resize_keyboard=True)
    )
    return EDIT_PLAN_NAME


async def edit_plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['edit_plan_data']['name'] = (update.message.text or "").strip()
    await update.message.reply_text(f"قیمت جدید را به تومان وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_PRICE


async def skip_edit_plan_name(update: Update, Context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر نام صرف‌نظر شد. قیمت جدید را به تومان وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_DAYS  # تایپوی نسخه قبلی اصلاح شد (برمی‌گردیم به قیمت یا روز؟ اینجا بهتر است به روز برگردیم)


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
        await update.message.reply_text(f"دسته‌بندی جدید را وارد کنید (یا {CMD_SKIP}).")
        return EDIT_PLAN_CATEGORY
    except ValueError:
        await update.message.reply_text("حجم را به صورت عدد وارد کنید.")
        return EDIT_PLAN_GB


async def skip_edit_plan_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر حجم صرف‌نظر شد. دسته‌بندی جدید را وارد کنید (یا {CMD_SKIP}).")
    return EDIT_PLAN_CATEGORY


async def edit_plan_category_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['edit_plan_data']['category'] = (update.message.text or "").strip()
    await finish_plan_edit(update, context)
    return ConversationHandler.END


async def skip_edit_plan_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("از تغییر دسته‌بندی صرف‌نظر شد.")
    await finish_plan_edit(update, context)
    return ConversationHandler.END


async def cancel_edit_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("ویرایش لغو شد.", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("🧩 بخش مدیریت پلن‌ها", reply_markup=_plan_menu_inline())
    return ConversationHandler.END


async def finish_plan_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_id = context.user_data.get('edit_plan_id')
    new_data = context.user_data.get('edit_plan_data')
    if not new_data:
        await update.message.reply_text("هیچ تغییری اعمال نشد.", reply_markup=ReplyKeyboardRemove())
    else:
        db.update_plan(plan_id, new_data)
        await update.message.reply_text("✅ پلن با موفقیت به‌روزرسانی شد!", reply_markup=ReplyKeyboardRemove())

    await update.message.reply_text("🧩 بخش مدیریت پلن‌ها", reply_markup=_plan_menu_inline())
    context.user_data.clear()
    return ConversationHandler.END


# ---------- Toggle/Delete ----------

async def admin_delete_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    حذف پلن و بازسازی همان لیست در همان پیام (ادیت).
    """
    q = update.callback_query
    await q.answer()
    try:
        plan_id = int(q.data.split('_')[-1])
    except Exception:
        await _send_or_edit(update, context, "❌ شناسه پلن نامعتبر است.", reply_markup=_inline_back_to_plan_menu(), parse_mode=None)
        return PLAN_MENU

    res = db.delete_plan_safe(plan_id)
    if res is None:
        await _send_or_edit(update, context, "❌ حذف پلن ناموفق بود. لطفاً بعداً تلاش کنید.", reply_markup=_inline_back_to_plan_menu(), parse_mode=None)
        return PLAN_MENU

    # پس از حذف، لیست را در همان پیام رفرش کن
    await list_plans_admin(update, context)
    return PLAN_MENU


async def admin_toggle_plan_visibility_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تغییر وضعیت نمایش/مخفی پلن، سپس بازسازی لیست در همان پیام (ادیت).
    """
    q = update.callback_query
    await q.answer()
    try:
        plan_id = int(q.data.split('_')[-1])
    except Exception:
        await _send_or_edit(update, context, "❌ شناسه پلن نامعتبر است.", reply_markup=_inline_back_to_plan_menu(), parse_mode=None)
        return PLAN_MENU

    db.toggle_plan_visibility(plan_id)
    # رفرش لیست در همان پیام
    await list_plans_admin(update, context)
    return PLAN_MENU


# ---------- بازگشت به منوی ادمین ----------

async def back_to_admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بازگشت به منوی ادمین. سعی می‌کنیم همان پیام ادیت شود؛
    اگر ادیت نشد (مثلاً پیام قبلی مدیا بوده)، پیام جدید ارسال می‌شود.
    """
    q = update.callback_query
    await q.answer()
    from bot.handlers.admin.common import admin_entry
    return await admin_entry(update, context)