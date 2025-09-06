# filename: bot/handlers/buy.py
# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from typing import List, Optional

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.error import BadRequest

import database as db
import hiddify_api
from bot import utils
from bot.constants import GET_CUSTOM_NAME, CMD_CANCEL, CMD_SKIP, PROMO_CODE_ENTRY
from bot.keyboards import get_main_menu_keyboard

try:
    from config import MULTI_SERVER_ENABLED, SERVERS, DEFAULT_SERVER_NAME, SUBCONVERTER_ENABLED, SUBCONVERTER_EXTRA_SERVERS
except Exception:
    MULTI_SERVER_ENABLED = False
    SERVERS = []
    DEFAULT_SERVER_NAME = None
    SUBCONVERTER_ENABLED = False
    SUBCONVERTER_EXTRA_SERVERS = []

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


def _get_global_discount_params() -> tuple[bool, float, Optional[datetime], Optional[datetime]]:
    """
    خواندن تنظیمات تخفیف همگانی از DB:
      - global_discount_enabled: 1/0
      - global_discount_percent: عدد (مثلاً 10)
      - global_discount_starts_at: اختیاری (ISO یا فرمت رایج)
      - global_discount_expires_at: اختیاری
    """
    enabled = str(db.get_setting("global_discount_enabled") or "0").lower() in ("1", "true", "on", "yes")
    try:
        percent = float(db.get_setting("global_discount_percent") or 0)
    except Exception:
        percent = 0.0
    starts = utils.parse_date_flexible(db.get_setting("global_discount_starts_at")) if db.get_setting("global_discount_starts_at") else None
    expires = utils.parse_date_flexible(db.get_setting("global_discount_expires_at")) if db.get_setting("global_discount_expires_at") else None
    return enabled, max(percent, 0.0), starts, expires


def _is_global_discount_active(now: datetime | None = None) -> tuple[bool, float]:
    enabled, percent, starts, expires = _get_global_discount_params()
    if not enabled or percent <= 0:
        return False, 0.0
    now = now or datetime.now().astimezone()
    if starts and now < starts:
        return False, 0.0
    if expires and now > expires:
        return False, 0.0
    return True, percent


def _short_label(p: dict) -> str:
    name = (p.get('name') or 'پلن')[:18]
    days = int(p.get('days', 0))
    gb = int(p.get('gb', 0))
    vol = _vol_label(gb)
    price_str = _short_price(p.get('price', 0))
    days_fa = utils.to_persian_digits(str(days))
    # یک برچسب کوتاه برای تخفیف همگانی اضافه می‌کنیم (اگر فعال باشد)
    gd_active, gd_percent = _is_global_discount_active()
    off_tag = f" | {int(gd_percent)}٪ آف" if gd_active and gd_percent > 0 else ""
    label = f"{name} | {days_fa} روز | {vol} | {price_str}{off_tag}"
    return label[:62] + "…" if len(label) > 63 else label


def _calc_promo_discount(user_id: int, plan_price: float, promo_code_in: str | None) -> tuple[int, str]:
    if not promo_code_in: return 0, ""
    code_data = db.get_promo_code(promo_code_in)
    if not code_data or not code_data['is_active']: return 0, "کد تخفیف نامعتبر است."
    if code_data['max_uses'] > 0 and code_data['used_count'] >= code_data['max_uses']: return 0, "ظرفیت استفاده از این کد به پایان رسیده است."
    if db.did_user_use_promo_code(user_id, promo_code_in): return 0, "شما قبلاً از این کد تخفیف استفاده کرده‌اید."
    if code_data['expires_at']:
        exp_dt = utils.parse_date_flexible(code_data['expires_at'])
        if exp_dt and datetime.now().astimezone() > exp_dt: return 0, "این کد تخفیف منقضی شده است."
    if code_data['first_purchase_only'] and db.get_user_purchase_count(user_id) > 0: return 0, "این کد تخفیف فقط برای خرید اول است."
    return int(float(plan_price) * (int(code_data['percent']) / 100.0)), ""


def _get_selected_server_name(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    if not MULTI_SERVER_ENABLED: return None
    for key in ("buy_server_name", "selected_server", "server_name"):
        val = context.user_data.get(key)
        if isinstance(val, str) and val.strip(): return val.strip()
    if isinstance(DEFAULT_SERVER_NAME, str) and DEFAULT_SERVER_NAME.strip(): return DEFAULT_SERVER_NAME.strip()
    if isinstance(SERVERS, list) and SERVERS and SERVERS[0].get("name"): return str(SERVERS[0]["name"])
    return None


def _pick_extra_servers(primary_name: Optional[str]) -> List[str]:
    extra = [str(n).strip() for n in (SUBCONVERTER_EXTRA_SERVERS or []) if str(n).strip() and str(n).strip() != primary_name]
    if not extra and MULTI_SERVER_ENABLED and SERVERS:
        cand = DEFAULT_SERVER_NAME or (SERVERS[0].get("name") if SERVERS else None)
        if cand and cand != primary_name: extra = [str(cand)]
    return list(dict.fromkeys(extra))


async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q: await q.answer()
    send_func = q.edit_message_text if q else update.message.reply_text
    if _maint_on():
        await send_func(_maint_msg()); return
    categories = db.get_plan_categories()
    if not categories:
        await send_func("در حال حاضر پلنی برای خرید موجود نیست."); return
    text, keyboard, row = "🛍️ لطفاً دسته‌بندی مورد نظر خود را انتخاب کنید:", [], []
    for cat in categories:
        row.append(InlineKeyboardButton(cat, callback_data=f"user_cat_{cat}"))
        if len(row) == 2: keyboard.append(row); row = []
    if row: keyboard.append(row)
    await send_func(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_plans_in_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    category = q.data.replace("user_cat_", "")
    plans = db.list_plans(only_visible=True, category=category)
    if not plans:
        await q.edit_message_text("در این دسته‌بندی پلنی یافت نشد."); return
    text, kb = f"پلن‌های دسته‌بندی «{category}»:", [[InlineKeyboardButton(_short_label(p), callback_data=f"user_buy_{p['plan_id']}")] for p in plans]
    kb.append([InlineKeyboardButton("🔙 بازگشت به دسته‌بندی‌ها", callback_data="back_to_cats")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if _maint_on():
        await q.answer(_maint_msg(), show_alert=True); return ConversationHandler.END
    try: plan_id = int(q.data.split('_')[-1])
    except Exception:
        await q.answer("شناسه پلن نامعتبر است.", show_alert=True); return ConversationHandler.END
    plan = db.get_plan(plan_id)
    if not plan or not plan.get('is_visible', 1):
        await q.answer("این پلن در دسترس نیست.", show_alert=True); return ConversationHandler.END
    context.user_data['buy_plan_id'] = plan_id
    try: await q.message.delete()
    except Exception: pass
    await context.bot.send_message(
        chat_id=q.from_user.id,
        text="لطفاً نام دلخواه برای سرویس‌تان را وارد کنید.\nبرای رد شدن از این مرحله، /skip را بزنید.",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
    )
    return GET_CUSTOM_NAME


async def get_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("لطفاً یک نام معتبر وارد کنید یا /skip بزنید."); return GET_CUSTOM_NAME
    if db.get_service_by_name(update.effective_user.id, name):
        await update.message.reply_text("⚠️ شما قبلاً سرویسی با این نام داشته‌اید. لطفاً نام دیگری انتخاب کنید."); return GET_CUSTOM_NAME
    context.user_data['buy_custom_name'] = name
    return await _ask_promo_code(update, context)


async def skip_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['buy_custom_name'] = ""; return await _ask_promo_code(update, context)


async def _ask_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "اگر کدتخفیف دارید وارد کنید؛ وگرنه /skip را بزنید.",
        reply_markup=ReplyKeyboardMarkup([['/skip', CMD_CANCEL]], resize_keyboard=True)
    )
    return PROMO_CODE_ENTRY


async def promo_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = (update.message.text or "").strip()
    context.user_data['buy_promo_code'] = "" if code.lower() == "/skip" else code
    return await _ask_purchase_confirm(update, context, custom_name=context.user_data.get('buy_custom_name', ''))


async def _ask_purchase_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_name: str):
    user_id = update.effective_user.id
    plan = db.get_plan(context.user_data.get('buy_plan_id'))
    if not plan:
        await update.message.reply_text("❌ پلن نامعتبر است.", reply_markup=get_main_menu_keyboard(user_id)); return ConversationHandler.END

    base_price = int(plan['price'])
    gd_active, gd_percent = _is_global_discount_active()
    gd_amount = int(round(base_price * (gd_percent / 100.0))) if (gd_active and gd_percent > 0) else 0
    price_after_global = max(0, base_price - gd_amount)

    promo_code = context.user_data.get('buy_promo_code')
    promo_discount, error_msg = _calc_promo_discount(user_id, price_after_global, promo_code)
    final_price = max(0, price_after_global - promo_discount)

    server_name = _get_selected_server_name(context)
    context.user_data['pending_buy'] = {
        'plan_id': plan['plan_id'],
        'custom_name': custom_name,
        'promo_code': promo_code,
        'final_price': final_price,
        'server_name': server_name
    }

    # ساخت متن قیمت
    lines = [f"قیمت: {_short_price(base_price)}"]
    if gd_amount > 0:
        lines.append(f"تخفیف همگانی ({int(gd_percent)}٪): {_short_price(gd_amount)}")
        lines.append(f"پس از تخفیف همگانی: {_short_price(price_after_global)}")
    if promo_code:
        if promo_discount > 0:
            lines.append(f"تخفیف کدتخفیف: {_short_price(promo_discount)}")
        elif error_msg:
            lines.append(f"(کد تخفیف نامعتبر: {error_msg})")
    lines.append(f"قیمت نهایی: {_short_price(final_price)}")
    price_block = "\n".join(lines)

    server_line = f"\nسرور: {server_name}" if MULTI_SERVER_ENABLED and server_name else ""
    text = f"""🛒 تایید خرید سرویس
نام سرویس: {custom_name or '(بدون نام)'}
مدت: {utils.to_persian_digits(str(plan['days']))} روز
حجم: {_vol_label(plan['gb'])}
{price_block}{server_line}
با تایید، مبلغ از کیف‌پول شما کسر شده و سرویس بلافاصله ساخته می‌شود.""".strip()

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ تایید خرید", callback_data="confirmbuy"),
                                InlineKeyboardButton("❌ انصراف", callback_data="cancelbuy")]])
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN); return ConversationHandler.END


async def confirm_purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data = context.user_data.get('pending_buy')
    if not data or not context.user_data.get('buy_plan_id'):
        await q.edit_message_text("⏳ زمان تایید شما منقضی شده است. لطفاً دوباره خرید را شروع کنید."); return
    await _do_purchase_confirmed(q, context, data.get('custom_name', ''))
    for k in ('pending_buy', 'buy_plan_id', 'buy_custom_name', 'buy_promo_code'): context.user_data.pop(k, None)


async def cancel_purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); context.user_data.pop('pending_buy', None)
    await q.edit_message_text("❌ خرید لغو شد.")


async def _do_purchase_confirmed(q, context: ContextTypes.DEFAULT_TYPE, custom_name: str):
    user_id, username = q.from_user.id, q.from_user.username
    data = context.user_data.get('pending_buy')
    if not data or not (plan := db.get_plan(data.get('plan_id'))):
        await q.edit_message_text("❌ پلن انتخاب‌شده نامعتبر است."); return
    txn_id = db.initiate_purchase_transaction(user_id, plan['plan_id'], data.get('final_price'))
    if not txn_id:
        await q.edit_message_text(f"❌ موجودی کافی نیست. لطفاً ابتدا حسابتان را شارژ کنید."); return
    try:
        await q.edit_message_text("⏳ در حال ایجاد سرویس شما...")
        note = f"tg:@{username}|id:{user_id}" if username else f"tg:id:{user_id}"
        gb_i = int(plan['gb'])
        default_name = "سرویس نامحدود" if gb_i == 0 else f"سرویس {utils.to_persian_digits(str(gb_i))} گیگ"
        provision = await hiddify_api.create_hiddify_user(
            plan_days=plan['days'], plan_gb=float(plan['gb']), user_telegram_id=note,
            custom_name=(custom_name or default_name), server_name=data.get('server_name')
        )
        if not provision or not provision.get("uuid"): raise RuntimeError("Failed to create service in primary panel")
        main_uuid, main_sublink, main_server_name = provision["uuid"], provision.get("full_link", ""), provision.get("server_name")
        db.finalize_purchase_transaction(txn_id, main_uuid, main_sublink, custom_name)
        if SUBCONVERTER_ENABLED:
            main_service_rec = db.get_service_by_uuid(main_uuid)
            if service_id := (main_service_rec or {}).get("service_id"):
                extra_servers = _pick_extra_servers(primary_name=main_server_name)
                for name in extra_servers:
                    try:
                        extra_prov = await hiddify_api.create_hiddify_user(
                            plan_days=plan['days'], plan_gb=float(plan['gb']), user_telegram_id=note,
                            custom_name=(custom_name or default_name), server_name=name
                        )
                        if extra_prov and extra_prov.get("uuid"):
                            db.add_service_endpoint(service_id, extra_prov["server_name"], extra_prov["uuid"], extra_prov.get("full_link", ""))
                    except Exception as e: logger.warning("Extra endpoint creation on %s failed: %s", name, e)
        if data.get('promo_code'): db.mark_promo_code_as_used(user_id, data['promo_code'])
        await _send_service_info_to_user(context, user_id, main_uuid)
    except Exception as e:
        logger.error("Purchase failed for user %s plan %s: %s", user_id, data.get('plan_id'), e, exc_info=True)
        db.cancel_purchase_transaction(txn_id)
        await context.bot.send_message(chat_id=user_id, text="❌ خطا در ایجاد سرویس. به پشتیبانی اطلاع دهید.", reply_markup=get_main_menu_keyboard(user_id))


async def _send_service_info_to_user(context, user_id, new_uuid):
    new_service_record = db.get_service_by_uuid(new_uuid)
    if not new_service_record:
        await context.bot.send_message(chat_id=user_id, text="❌ خطای داخلی: سرویس ساخته شد اما در دیتابیس یافت نشد.")
        return

    server_name = new_service_record.get("server_name")
    user_data = await hiddify_api.get_user_info(new_uuid, server_name=server_name)

    if user_data:
        admin_default_type = utils.normalize_link_type(db.get_setting("default_sub_link_type") or "sub")
        config_name = (user_data.get('name', 'config') if isinstance(user_data, dict) else 'config') or 'config'
        safe_name = str(config_name).replace(' ', '_')

        base_main = utils.build_subscription_url(new_uuid) \
                    or new_service_record.get('sub_link') \
                    or utils.build_subscription_url(new_uuid, server_name=server_name)

        final_link = ""
        if admin_default_type == "unified" and SUBCONVERTER_ENABLED:
            sources: List[str] = []
            main_direct = new_service_record.get('sub_link') or utils.build_subscription_url(new_uuid, server_name=server_name)
            if isinstance(main_direct, str) and main_direct.strip():
                sources.append(main_direct.strip())
            try:
                endpoints = db.list_service_endpoints(new_service_record.get("service_id"))
                for ep in endpoints or []:
                    ep_link = (ep.get("sub_link") or "").strip()
                    if ep_link and ep_link not in sources:
                        sources.append(ep_link)
            except Exception:
                pass
            if len(sources) > 1:
                target = utils.link_type_to_subconverter_target(admin_default_type)
                unified_url = utils.build_subconverter_link(sources, target=target)
                if unified_url:
                    final_link = unified_url

        if not final_link:
            if admin_default_type == "sub":
                final_link = base_main
            else:
                t = admin_default_type.replace('clashmeta', 'clash-meta')
                final_link = f"{base_main}/{t}/?name={safe_name}"

        qr_bio = utils.make_qr_bytes(final_link)
        caption = utils.create_service_info_caption(
            user_data, service_db_record=new_service_record, title="🎉 سرویس شما با موفقیت ساخته شد!", override_sub_url=final_link
        )
        inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📚 راهنمای اتصال", callback_data="guide_connection"), InlineKeyboardButton("📋 سرویس‌های من", callback_data="back_to_services")]])
        await context.bot.send_photo(chat_id=user_id, photo=InputFile(qr_bio), caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=inline_kb)
        await context.bot.send_message(chat_id=user_id, text="منوی اصلی:", reply_markup=get_main_menu_keyboard(user_id))
    else:
        await context.bot.send_message(chat_id=user_id, text="✅ خرید انجام شد، اما دریافت اطلاعات سرویس با خطا مواجه شد. از «📋 سرویس‌های من» استفاده کنید.", reply_markup=get_main_menu_keyboard(user_id))