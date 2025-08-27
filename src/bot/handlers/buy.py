# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.error import BadRequest

import database as db
import hiddify_api
from bot import utils
from bot.constants import GET_CUSTOM_NAME, CMD_CANCEL, CMD_SKIP, PROMO_CODE_ENTRY
from bot.keyboards import get_main_menu_keyboard

# Optional multi-server configs (safe defaults if not present in config.py)
try:
    from config import MULTI_SERVER_ENABLED, SERVERS, DEFAULT_SERVER_NAME
except Exception:
    MULTI_SERVER_ENABLED = False
    SERVERS = []
    DEFAULT_SERVER_NAME = None

logger = logging.getLogger(__name__)


def _maint_on() -> bool:
    val = db.get_setting("maintenance_enabled")
    return str(val).lower() in ("1", "true", "on", "yes")


def _maint_msg() -> str:
    return db.get_setting("maintenance_message") or "⛔️ ربات در حال بروزرسانی است. لطفاً کمی بعد مراجعه کنید."


def _short_price(price: float) -> str:
    return utils.format_toman(price, persian_digits=True)


def _vol_label(gb: int) -> str:
    g = int(gb)
    return "نامحدود" if g == 0 else f"{utils.to_persian_digits(str(g))} گیگ"


def _short_label(p: dict) -> str:
    name = (p.get('name') or 'پلن')[:18]
    days = int(p.get('days', 0))
    gb = int(p.get('gb', 0))
    vol = _vol_label(gb)
    price_str = _short_price(p.get('price', 0))
    days_fa = utils.to_persian_digits(str(days))
    label = f"{name} | {days_fa} روز | {vol} | {price_str}"
    return label[:62] + "…" if len(label) > 63 else label


def _calc_promo_discount(user_id: int, plan_price: float, promo_code_in: str | None) -> tuple[int, str]:
    if not promo_code_in:
        return 0, ""

    code_data = db.get_promo_code(promo_code_in)
    if not code_data or not code_data['is_active']:
        return 0, "کد تخفیف نامعتبر است."

    if code_data['max_uses'] > 0 and code_data['used_count'] >= code_data['max_uses']:
        return 0, "ظرفیت استفاده از این کد به پایان رسیده است."

    if db.did_user_use_promo_code(user_id, promo_code_in):
        return 0, "شما قبلاً از این کد تخفیف استفاده کرده‌اید."

    if code_data['expires_at']:
        exp_dt = utils.parse_date_flexible(code_data['expires_at'])
        if exp_dt and datetime.now().astimezone() > exp_dt:
            return 0, "این کد تخفیف منقضی شده است."

    if code_data['first_purchase_only'] and db.get_user_purchase_count(user_id) > 0:
        return 0, "این کد تخفیف فقط برای خرید اول است."

    discount = int(float(plan_price) * (int(code_data['percent']) / 100.0))
    return discount, ""


def _get_selected_server_name(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """
    انتخاب نام سرور بر اساس داده‌های کاربر یا تنظیمات پیش‌فرض.
    اگر MULTI_SERVER_ENABLED نباشد، None برمی‌گردد تا API از حالت تک‌سرور استفاده کند.
    """
    if not MULTI_SERVER_ENABLED:
        return None
    # اگر از قبل در جریان گفت‌وگو یا جای دیگر ست شده باشد
    for key in ("buy_server_name", "selected_server", "server_name"):
        val = context.user_data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # پیش‌فرض از تنظیمات
    if isinstance(DEFAULT_SERVER_NAME, str) and DEFAULT_SERVER_NAME.strip():
        return DEFAULT_SERVER_NAME.strip()
    # اگر لیست سرورها موجود است، اولی
    if isinstance(SERVERS, list) and SERVERS:
        name = SERVERS[0].get("name")
        if name:
            return str(name)
    return None


# --- لیست دسته‌بندی و پلن‌ها ---
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


# --- شروع خرید → نام → کد تخفیف ---
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

    # فعلاً انتخاب سرور را به تنظیمات پیش‌فرض واگذار می‌کنیم (در صورت تمایل، می‌توان مرحله انتخاب سرور را هم اضافه کرد)
    # server_name = _get_selected_server_name(context)
    # context.user_data['buy_server_name'] = server_name

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

    context.user_data['buy_custom_name'] = name
    return await _ask_promo_code(update, context)


async def skip_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['buy_custom_name'] = ""
    return await _ask_promo_code(update, context)


async def _ask_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "اگر کدتخفیف دارید وارد کنید؛ وگرنه /skip را بزنید.",
        reply_markup=ReplyKeyboardMarkup([['/skip', CMD_CANCEL]], resize_keyboard=True)
    )
    return PROMO_CODE_ENTRY


async def promo_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = (update.message.text or "").strip()
    if code.lower() == "/skip":
        code = ""
    context.user_data['buy_promo_code'] = code
    return await _ask_purchase_confirm(update, context, custom_name=context.user_data.get('buy_custom_name', ''))


# --- مرحله تأیید خرید ---
async def _ask_purchase_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_name: str):
    user_id = update.effective_user.id
    plan_id = context.user_data.get('buy_plan_id')
    plan = db.get_plan(plan_id) if plan_id else None

    if not plan:
        await update.message.reply_text("❌ پلن انتخاب‌شده نامعتبر است.", reply_markup=get_main_menu_keyboard(user_id))
        return ConversationHandler.END

    promo_code = context.user_data.get('buy_promo_code')
    discount, error_msg = _calc_promo_discount(user_id, plan['price'], promo_code)
    final_price = max(0, int(plan['price']) - discount)

    # انتخاب سرور جهت نمایش در تاییدیه (و استفاده حین ساخت سرویس)
    server_name = _get_selected_server_name(context)

    context.user_data['pending_buy'] = {
        'plan_id': plan_id,
        'custom_name': custom_name,
        'promo_code': promo_code,
        'final_price': final_price,
        'server_name': server_name
    }

    volume_text = _vol_label(int(plan['gb']))
    price_text = utils.format_toman(plan['price'], persian_digits=True)
    if discount > 0:
        discount_text = utils.format_toman(discount, persian_digits=True)
        final_price_text = utils.format_toman(final_price, persian_digits=True)
        price_line = f"قیمت: {price_text}\nتخفیف: {discount_text}\nقیمت نهایی: {final_price_text}"
    else:
        price_line = f"قیمت: {price_text}"
        if promo_code and error_msg:
            price_line += f"\n(کد تخفیف نامعتبر: {error_msg})"

    server_line = f"\nسرور: {server_name}" if MULTI_SERVER_ENABLED and server_name else ""

    text = f"""
🛒 تایید خرید سرویس

نام سرویس: {custom_name or '(بدون نام)'}
مدت: {utils.to_persian_digits(str(plan['days']))} روز
حجم: {volume_text}
{price_line}{server_line}

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
    context.user_data.pop('buy_plan_id', None)
    context.user_data.pop('buy_custom_name', None)
    context.user_data.pop('buy_promo_code', None)


async def cancel_purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.pop('pending_buy', None)
    try:
        await q.edit_message_text("❌ خرید لغو شد.")
    except BadRequest:
        await context.bot.send_message(chat_id=q.from_user.id, text="❌ خرید لغو شد.")


# --- ساخت سرویس پس از تایید ---
async def _do_purchase_confirmed(q, context: ContextTypes.DEFAULT_TYPE, custom_name: str):
    user_id = q.from_user.id
    username = q.from_user.username
    data = context.user_data.get('pending_buy')

    # بررسی اطلاعات پایه
    validation_result = await _validate_purchase_data(context, user_id, data)
    if validation_result:
        # اگر پیام خطا وجود دارد
        await _send_error_message(q, context, validation_result)
        return

    plan_id = data.get('plan_id')
    final_price = data.get('final_price')
    promo_code = data.get('promo_code')
    plan = db.get_plan(plan_id)

    # آغاز تراکنش
    txn_id = db.initiate_purchase_transaction(user_id, plan_id, final_price)
    if not txn_id:
        await q.edit_message_text(f"❌ موجودی کافی نیست. لطفاً ابتدا حسابتان را شارژ کنید.")
        return

    try:
        await _notify_purchase_started(q, context, user_id)

        # ایجاد سرویس در پنل هیدیفای
        new_uuid, sub_link = await _create_service_in_panel(
            context, user_id, username, plan, custom_name, data.get('server_name')
        )

        if not new_uuid:
            raise RuntimeError("Failed to create service in panel")

        # نهایی کردن تراکنش در پایگاه داده (server_name در finalize با sub_link نیز ذخیره/تشخیص داده می‌شود)
        db.finalize_purchase_transaction(txn_id, new_uuid, sub_link, custom_name)

        # اعمال کد تخفیف در صورت استفاده
        if promo_code:
            db.mark_promo_code_as_used(user_id, promo_code)

        # ارسال اطلاعات سرویس به کاربر
        await _send_service_info_to_user(context, user_id, new_uuid)

    except Exception as e:
        logger.error("Purchase failed for user %s plan %s: %s", user_id, plan_id, e, exc_info=True)
        db.cancel_purchase_transaction(txn_id)
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ خطا در ایجاد سرویس. لطفاً بعداً دوباره تلاش کنید یا به پشتیبانی اطلاع دهید.",
            reply_markup=get_main_menu_keyboard(user_id)
        )


async def _validate_purchase_data(context, user_id, data):
    """بررسی صحت داده‌های خرید"""
    if not data:
        return "اطلاعات خرید یافت نشد."

    plan_id = data.get('plan_id')
    plan = db.get_plan(plan_id) if plan_id else None

    if not plan:
        return "پلن انتخاب‌شده نامعتبر است."

    return None  # بدون خطا


async def _notify_purchase_started(q, context, user_id):
    """اطلاع‌رسانی به کاربر درباره شروع فرآیند خرید"""
    try:
        await q.edit_message_text("⏳ در حال ایجاد سرویس شما...")
    except BadRequest:
        await context.bot.send_message(chat_id=user_id, text="⏳ در حال ایجاد سرویس شما...")


async def _create_service_in_panel(context, user_id, username, plan, custom_name, server_name: str | None):
    """ایجاد سرویس در پنل هیدیفای (با پشتیبانی چندسرور)"""
    gb_i = int(plan['gb'])
    default_name = "سرویس نامحدود" if gb_i == 0 else f"سرویس {utils.to_persian_digits(str(gb_i))} گیگ"
    final_name = custom_name or default_name

    note = f"tg:@{username}|id:{user_id}" if username else f"tg:id:{user_id}"

    provision = await hiddify_api.create_hiddify_user(
        plan_days=plan['days'],
        plan_gb=float(plan['gb']),
        user_telegram_id=note,
        custom_name=final_name,
        server_name=server_name  # ممکن است None باشد و در این صورت سرور پیش‌فرض انتخاب می‌شود
    )

    if not provision or not provision.get("uuid"):
        return None, None

    return provision["uuid"], provision.get('full_link', '')


async def _send_service_info_to_user(context, user_id, new_uuid):
    """ارسال اطلاعات سرویس به کاربر"""
    new_service_record = db.get_service_by_uuid(new_uuid)
    server_name = (new_service_record or {}).get("server_name")
    user_data = await hiddify_api.get_user_info(new_uuid, server_name=server_name)

    if user_data:
        # ترجیح لینک ذخیره‌شده در DB (که دقیقاً مربوط به سرور ساخته‌شده است)
        sub_url = (new_service_record or {}).get('sub_link') or utils.build_subscription_url(new_uuid, server_name=server_name)
        qr_bio = utils.make_qr_bytes(sub_url)
        caption = utils.create_service_info_caption(
            user_data,
            service_db_record=new_service_record,
            title="🎉 سرویس شما با موفقیت ساخته شد!"
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


async def _send_error_message(q, context, error_message):
    """ارسال پیام خطا به کاربر"""
    try:
        await q.edit_message_text(f"❌ {error_message}")
    except BadRequest:
        await context.bot.send_message(
            chat_id=q.from_user.id,
            text=f"❌ {error_message}",
            reply_markup=get_main_menu_keyboard(q.from_user.id)
        )