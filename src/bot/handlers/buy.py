# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.error import BadRequest

import database as db
import hiddify_api
from bot import utils
from bot.constants import GET_CUSTOM_NAME, CMD_CANCEL, CMD_SKIP
from bot.keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)

def _maint_on() -> bool:
    val = db.get_setting("maintenance_enabled")
    return str(val).lower() in ("1", "true", "on", "yes")

def _maint_msg() -> str:
    return db.get_setting("maintenance_message") or "⛔️ ربات در حال بروزرسانی است. لطفاً کمی بعد مراجعه کنید."

def _short_price(price: float) -> str:
    # قیمت با جداکننده هزار و ارقام فارسی
    return utils.format_toman(price, persian_digits=True)

def _vol_label(gb: int) -> str:
    # حجم با ارقام فارسی و واژه فارسی برای جلوگیری از به‌هم‌ریختگی RTL
    g = int(gb)
    return "نامحدود" if g == 0 else f"{utils.to_persian_digits(str(g))} گیگابایت"

def _short_label(p: dict) -> str:
    # ترتیب ثابت: نام | روز | حجم | قیمت (همه با ارقام فارسی)
    name = (p.get('name') or 'پلن')[:18]
    days = int(p.get('days', 0))
    gb = int(p.get('gb', 0))
    vol = _vol_label(gb)
    price_str = _short_price(p.get('price', 0))
    days_fa = utils.to_persian_digits(str(days))
    label = f"{name} | {days_fa} روز | {vol} | {price_str}"
    # در صورت طولانی بودن، کوتاه‌ترش کن
    return label[:62] + "…" if len(label) > 63 else label

# --------------------------
# لیست دسته‌بندی و پلن‌ها
# --------------------------
async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()
        send_func = q.edit_message_text
    else:
        send_func = update.message.reply_text

    if _maint_on():
        await send_func(_maint_msg())
        return

    categories = db.get_plan_categories()
    if not categories:
        await send_func("در حال حاضر پلنی برای خرید موجود نیست.")
        return

    text = "🛍️ لطفاً دسته‌بندی مورد نظر خود را انتخاب کنید:"
    keyboard, row = [], []
    for cat in categories:
        row.append(InlineKeyboardButton(cat, callback_data=f"user_cat_{cat}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await send_func(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_plans_in_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    category = q.data.replace("user_cat_", "")

    plans = db.list_plans(only_visible=True, category=category)
    if not plans:
        await q.edit_message_text("در این دسته‌بندی پلنی یافت نشد.")
        return

    text = f"پلن‌های دسته‌بندی «{category}»:"
    kb = []
    for p in plans:
        kb.append([InlineKeyboardButton(_short_label(p), callback_data=f"user_buy_{p['plan_id']}")])

    kb.append([InlineKeyboardButton("🔙 بازگشت به دسته‌بندی‌ها", callback_data="back_to_cats")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

# --------------------------
# شروع خرید → گرفتن نام
# --------------------------
async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if _maint_on():
        await q.answer(_maint_msg(), show_alert=True)
        return ConversationHandler.END

    try:
        plan_id = int(q.data.split('_')[-1])
    except Exception:
        await q.answer("شناسه پلن نامعتبر است.", show_alert=True)
        return ConversationHandler.END

    plan = db.get_plan(plan_id)
    if not plan or not plan.get('is_visible', 1):
        await q.answer("این پلن در دسترس نیست.", show_alert=True)
        return ConversationHandler.END

    context.user_data['buy_plan_id'] = plan_id
    try:
        await q.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=q.from_user.id,
        text="لطفاً نام دلخواه برای سرویس‌تان را وارد کنید.\nبرای رد شدن از این مرحله، /skip را بزنید.",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
    )
    return GET_CUSTOM_NAME

async def get_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("لطفاً یک نام معتبر وارد کنید یا /skip بزنید.")
        return GET_CUSTOM_NAME
    if db.get_service_by_name(update.effective_user.id, name):
        await update.message.reply_text("⚠️ شما قبلاً سرویسی با این نام داشته‌اید. لطفاً نام دیگری انتخاب کنید.")
        return GET_CUSTOM_NAME

    return await _ask_purchase_confirm(update, context, custom_name=name)

async def skip_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _ask_purchase_confirm(update, context, custom_name="")

# --------------------------
# مرحله تأیید خرید
# --------------------------
async def _ask_purchase_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_name: str):
    user_id = update.effective_user.id
    plan_id = context.user_data.get('buy_plan_id')
    plan = db.get_plan(plan_id) if plan_id else None

    if not plan:
        await update.message.reply_text("❌ پلن انتخاب‌شده نامعتبر است.", reply_markup=get_main_menu_keyboard(user_id))
        return ConversationHandler.END

    context.user_data['pending_buy'] = {
        'plan_id': plan_id,
        'custom_name': custom_name
    }

    volume_text = _vol_label(int(plan['gb']))
    price_text = utils.format_toman(plan['price'], persian_digits=True)
    days_fa = utils.to_persian_digits(str(plan['days']))

    text = f"""
🛒 تایید خرید سرویس

نام سرویس: {custom_name or '(بدون نام)'}
مدت: {days_fa} روز
حجم: {volume_text}
قیمت: {price_text}

با تایید، مبلغ از کیف‌پول شما کسر شده و سرویس بلافاصله ساخته می‌شود.
ادامه می‌دهید؟
    """.strip()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید خرید", callback_data="confirmbuy")],
        [InlineKeyboardButton("❌ انصراف", callback_data="cancelbuy")]
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END

async def confirm_purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    data = context.user_data.get('pending_buy')
    plan_id = context.user_data.get('buy_plan_id')
    if not data or not plan_id:
        try:
            await q.edit_message_text("⏳ زمان تایید شما منقضی شده است. لطفاً دوباره خرید را شروع کنید.")
        except BadRequest:
            await context.bot.send_message(chat_id=q.from_user.id, text="⏳ زمان تایید شما منقضی شده است. دوباره از «🛍️ خرید سرویس» اقدام کنید.")
        return

    custom_name = data.get('custom_name', '')
    await _do_purchase_confirmed(q, context, custom_name)
    context.user_data.pop('pending_buy', None)

async def cancel_purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.pop('pending_buy', None)
    try:
        await q.edit_message_text("❌ خرید لغو شد.")
    except BadRequest:
        await context.bot.send_message(chat_id=q.from_user.id, text="❌ خرید لغو شد.")

# --------------------------
# ساخت سرویس پس از تایید
# --------------------------
async def _do_purchase_confirmed(q, context: ContextTypes.DEFAULT_TYPE, custom_name: str):
    user_id = q.from_user.id
    username = q.from_user.username
    plan_id = context.user_data.get('buy_plan_id')
    plan = db.get_plan(plan_id) if plan_id else None

    if not plan:
        await context.bot.send_message(chat_id=user_id, text="❌ پلن انتخاب‌شده نامعتبر است.", reply_markup=get_main_menu_keyboard(user_id))
        return

    txn_id = db.initiate_purchase_transaction(user_id, plan_id)
    if not txn_id:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ موجودی کافی نیست. لطفاً ابتدا حسابتان را شارژ کنید.",
            reply_markup=ReplyKeyboardMarkup([["💰 موجودی و شارژ حساب"]], resize_keyboard=True)
        )
        return

    try:
        try:
            await q.edit_message_text("⏳ در حال ایجاد سرویس شما...")
        except BadRequest:
            await context.bot.send_message(chat_id=user_id, text="⏳ در حال ایجاد سرویس شما...")

        # نام پیشفرض برای نامحدود
        gb_i = int(plan['gb'])
        default_name = "سرویس نامحدود" if gb_i == 0 else f"سرویس {utils.to_persian_digits(str(gb_i))} گیگابایت"
        final_name = custom_name or default_name

        note = f"tg:@{username}|id:{user_id}" if username else f"tg:id:{user_id}"

        provision = await hiddify_api.create_hiddify_user(
            plan_days=plan['days'],
            plan_gb=float(plan['gb']),
            user_telegram_id=note,
            custom_name=final_name
        )
        if not provision or not provision.get("uuid"):
            raise RuntimeError("Provisioning failed or no uuid returned.")

        new_uuid = provision["uuid"]
        sub_link = provision.get('full_link', '')
        db.finalize_purchase_transaction(txn_id, new_uuid, sub_link, final_name)

        user_data = await hiddify_api.get_user_info(new_uuid)
        if user_data:
            sub_url = utils.build_subscription_url(new_uuid)
            qr_bio = utils.make_qr_bytes(sub_url)
            caption = utils.create_service_info_caption(user_data, title="🎉 سرویس شما با موفقیت ساخته شد!")

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

            await context.bot.send_message(
                chat_id=user_id,
                text="منوی اصلی:",
                reply_markup=get_main_menu_keyboard(user_id)
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ خرید انجام شد، اما دریافت اطلاعات سرویس با خطا مواجه شد. از «📋 سرویس‌های من» استفاده کنید.",
                reply_markup=get_main_menu_keyboard(user_id)
            )

    except Exception as e:
        logger.error("Purchase failed for user %s plan %s: %s", user_id, plan_id, e, exc_info=True)
        db.cancel_purchase_transaction(txn_id)
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ خطا در ایجاد سرویس. لطفاً بعداً دوباره تلاش کنید یا به پشتیبانی اطلاع دهید.",
            reply_markup=get_main_menu_keyboard(user_id)
        )