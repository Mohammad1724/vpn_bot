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
        [InlineKeyboardButton("🔙 بازگشت به مدیریت پلن‌ها", callback_data="admin_plans")]
    ])


def _inline_header_for_list() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به مدیریت پلن‌ها", callback_data="admin_plans")]
    ])


def _plan_card_keyboard(plan_id: int, is_visible: bool) -> InlineKeyboardMarkup:
    vis_label = "👁️ مخفی‌کردن" if is_visible else "👁️‍🗨️ نمایش‌دادن"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✏️ ویرایش", callback_data=f"admin_edit_plan_{plan_id}"),
        InlineKeyboardButton(vis_label, callback_data=f"admin_toggle_plan_{plan_id}"),
        InlineKeyboardButton("🗑️ حذف", callback_data=f"admin_delete_plan_{plan_id}")
    ]])


def _format_plan_card_text(p: dict) -> str:
    """
    متن کارت پلن خوانا و ساده (بدون Markdown پیچیده برای جلوگیری از خطای رندرینگ).
    """
    pid = p.get("plan_id", "-")
    name = p.get("name") or "-"
    price = int(float(p.get("price") or 0))
    days = int(p.get("days") or 0)
    gb = int(p.get("gb") or 0)
    cat = p.get("category") or "-"
    state = "نمایش ✅" if p.get("is_visible") else "مخفی ❌"

    text = (
        f"پلن #{pid}\n"
        f"نام: {name}\n"
        f"دسته‌بندی: {cat}\n"
        f"قیمت: {price:,} تومان\n"
        f"مدت: {days} روز | حجم: {gb} گیگ\n"
        f"وضعیت: {state}"
    )
    return text


# ---------- Helper: edit current message if callback, else send ----------

async def _send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    q = getattr(update, "callback_query", None)
    if q:
        try:
            await q.answer()
        except Exception:
            pass
        try:
            await q.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
        except BadRequest:
            # اگر ادیت نشد، پیام جدید ارسال کن
            await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)


# ---------- Store for plan-list messages (cards) ----------

def _get_pl_store(context: ContextTypes.DEFAULT_TYPE):
    store = context.user_data.get('plan_list_store')
    if not store:
        store = {'chat_id': None, 'msg_ids': [], 'anchor_msg_id': None}
        context.user_data['plan_list_store'] = store
    return store


async def _store_sent_message(context: ContextTypes.DEFAULT_TYPE, msg):
    st = _get_pl_store(context)
    st['chat_id'] = msg.chat_id
    st['msg_ids'].append(msg.message_id)


async def _set_anchor_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    st = _get_pl_store(context)
    st['chat_id'] = q.message.chat_id
    st['anchor_msg_id'] = q.message.message_id


async def _purge_plan_list_messages(context: ContextTypes.DEFAULT_TYPE):
    st = context.user_data.get('plan_list_store')
    if not st or not st.get('msg_ids'):
        return
    chat_id = st.get('chat_id')
    for mid in st['msg_ids']:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
    st['msg_ids'].clear()


# ---------- Plan management menu ----------

async def plan_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بازگشت به منوی مدیریت پلن‌ها:
    - کارت‌های لیست موجود پاک می‌شوند
    - همان پیام سرتیتر (anchor) ادیت می‌شود (یا اگر نبود، پیام جدید ارسال می‌شود)
    """
    await _purge_plan_list_messages(context)
    await _send_or_edit(update, context, "🧩 بخش مدیریت پلن‌ها", reply_markup=_plan_menu_inline(), parse_mode=None)
    return PLAN_MENU


async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش لیست پلن‌ها به‌صورت کارت‌های جدا+یک پیام سرتیتر (anchor).
    - پیام Callback فعلی به سرتیتر تبدیل می‌شود و فقط دکمه بازگشت دارد.
    - برای هر پلن یک کارت خوانا با دکمه‌های کنترل ارسال می‌شود.
    - هنگام بازگشت به مدیریت پلن‌ها، فقط کارت‌ها پاک و سرتیتر ادیت می‌شود.
    """
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        # پیام فعلی را به سرتیتر تبدیل و به‌عنوان anchor ذخیره کن
        await _set_anchor_from_callback(update, context)
        try:
            await q.edit_message_text(
                text="📋 لیست پلن‌ها (برای مدیریت از دکمه‌های کارت هر پلن استفاده کنید):",
                reply_markup=_inline_header_for_list(),
                parse_mode=None,
                disable_web_page_preview=True
            )
        except BadRequest:
            pass

    # پاکسازی کارت‌های قبلی (اگر بودند)
    await _purge_plan_list_messages(context)

    plans = db.list_plans(only_visible=False)
    if not plans:
        # اگر پلنی نبود، همان پیام سرتیتر را به «هیچ پلنی ندارد» ادیت کن
        await _send_or_edit(update, context, "هیچ پلنی تعریف نشده است.", reply_markup=_inline_back_to_plan_menu(), parse_mode=None)
        return PLAN_MENU

    # برای هر پلن یک کارت ارسال کن
    for p in plans:
        text = _format_plan_card_text(p)
        kb = _plan_card_keyboard(p["plan_id"], bool(p.get("is_visible", 1)))
        msg = await context.bot.send_message(chat_id=q.from_user.id if q else update.effective_chat.id, text=text, reply_markup=kb, parse_mode=None)
        await _store_sent_message(context, msg)

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
        await _send_or_edit(update, context, "پلن یافت نشد.", reply_markup=_inline_back_to_plan_menu(), parse_mode=None)
        return ConversationHandler.END

    plan = db.get_plan(plan_id)
    if not plan:
        await _send_or_edit(update, context, "پلن یافت نشد.", reply_markup=_inline_back_to_plan_menu(), parse_mode=None)
        return ConversationHandler.END

    context.user_data['edit_plan_id'] = plan_id
    context.user_data['edit_plan_data'] = {}

    await q.message.reply_text(
        f"در حال ویرایش پلن: {plan['name']}\n\nنام جدید را وارد کنید. برای رد شدن، {CMD_SKIP} را بزنید.",
        parse_mode=None,
        reply_markup=ReplyKeyboardMarkup([[CMD_SKIP], [CMD_CANCEL]], resize_keyboard=True)
    )
    return EDIT_PLAN_NAME


async def edit_plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['edit_plan_data']['name'] = (update.message.text or "").strip()
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
    حذف کارت پلن و بروزسازی نمای لیست.
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

    # کارت فعلی را حذف کن
    try:
        await q.message.delete()
    except Exception:
        pass
    # از لیست پیام‌های ذخیره‌شده هم حذفش کن
    st = _get_pl_store(context)
    if st.get('msg_ids') and q.message and q.message.message_id in st['msg_ids']:
        try:
            st['msg_ids'].remove(q.message.message_id)
        except Exception:
            pass

    await q.answer("پلن حذف شد.", show_alert=False)
    return PLAN_MENU


async def admin_toggle_plan_visibility_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تغییر وضعیت نمایش/مخفی پلن و رفرش کارت همان پلن.
    """
    q = update.callback_query
    await q.answer()
    try:
        plan_id = int(q.data.split('_')[-1])
    except Exception:
        await _send_or_edit(update, context, "❌ شناسه پلن نامعتبر است.", reply_markup=_inline_back_to_plan_menu(), parse_mode=None)
        return PLAN_MENU

    db.toggle_plan_visibility(plan_id)
    # کارت را رفرش کن
    p = db.get_plan(plan_id)
    if not p:
        # اگر پلن حذف شده بود یا یافت نشد، کارت را پاک کن
        try:
            await q.message.delete()
        except Exception:
            pass
        return PLAN_MENU

    text = _format_plan_card_text(p)
    kb = _plan_card_keyboard(p["plan_id"], bool(p.get("is_visible", 1)))
    try:
        await q.edit_message_text(text=text, reply_markup=kb, parse_mode=None, disable_web_page_preview=True)
    except BadRequest:
        # اگر ادیت نشد، پیام جدید بفرست و قدیمی را پاک کن
        try:
            new_msg = await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=None, disable_web_page_preview=True)
            await q.message.delete()
            await _store_sent_message(context, new_msg)
        except Exception:
            pass
    return PLAN_MENU


# ---------- بازگشت به منوی ادمین (anchor ادیت می‌شود) ----------

async def back_to_admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پاکسازی کارت‌ها و بازگشت به منوی ادمین.
    """
    q = update.callback_query
    await q.answer()
    await _purge_plan_list_messages(context)
    # ادیت پیام فعلی به منوی ادمین در common.admin_entry انجام می‌شود
    from bot.handlers.admin.common import admin_entry
    return await admin_entry(update, context)