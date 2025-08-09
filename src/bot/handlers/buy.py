# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from bot.constants import CMD_SKIP, GET_CUSTOM_NAME
from bot.keyboards import get_main_menu_keyboard
from telegram.error import BadRequest, Forbidden
import database as db
import hiddify_api

async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans(only_visible=True)
    if not plans:
        await update.message.reply_text("متأسفانه در حال حاضر هیچ پلنی موجود نیست.")
        return
    keyboard = [[InlineKeyboardButton(f"{p['name']} - {p['days']} روزه {p['gb']} گیگ - {p['price']:.0f} تومان", callback_data=f"user_buy_{p['plan_id']}")] for p in plans]
    await update.message.reply_text("لطفاً پلن مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split('_')[-1])
    transaction_id = db.initiate_purchase_transaction(query.from_user.id, plan_id)
    if not transaction_id:
        user = db.get_or_create_user(query.from_user.id)
        plan = db.get_plan(plan_id)
        await query.edit_message_text(f"موجودی شما کافی نیست.\nموجودی: {user['balance']:.0f} تومان\nقیمت پلن: {plan['price']:.0f} تومان")
        return ConversationHandler.END
    context.user_data['transaction_id'] = transaction_id
    context.user_data['plan_to_buy_id'] = plan_id
    await query.edit_message_text(
        f"پلن انتخاب شد.\n\nیک نام دلخواه برای این سرویس وارد کنید (مثلاً: گوشی شخصی).\nبرای استفاده از نام پیش‌فرض، {CMD_SKIP} را ارسال کنید.",
        reply_markup=None
    )
    return GET_CUSTOM_NAME

async def get_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    custom_name = update.message.text
    if len(custom_name) > 50:
        await update.message.reply_text("نام وارد شده طولانی است (حداکثر ۵۰ کاراکتر).")
        return GET_CUSTOM_NAME
    context.user_data['custom_name'] = custom_name
    await create_service_after_name(update.message, context)
    return ConversationHandler.END

async def skip_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['custom_name'] = ""
    await create_service_after_name(update.message, context)
    return ConversationHandler.END

async def create_service_after_name(message: Update.message, context: ContextTypes.DEFAULT_TYPE):
    user_id = message.chat_id
    plan_id = context.user_data.get('plan_to_buy_id')
    transaction_id = context.user_data.get('transaction_id')
    custom_name_input = context.user_data.get('custom_name', "")
    if not all([plan_id, transaction_id]):
        await message.reply_text("خطای داخلی رخ داد. لطفاً دوباره تلاش کنید.", reply_markup=get_main_menu_keyboard(user_id))
        context.user_data.clear()
        return

    plan = db.get_plan(plan_id)
    custom_name = custom_name_input if custom_name_input else f"سرویس {plan['gb']} گیگ"

    msg_loading = await message.reply_text("در حال ساخت سرویس... ⏳", reply_markup=get_main_menu_keyboard(user_id))
    result = await hiddify_api.create_hiddify_user(plan['days'], plan['gb'], user_id, custom_name=custom_name)

    if result and result.get('uuid'):
        db.finalize_purchase_transaction(transaction_id, result['uuid'], result['full_link'], custom_name)
        referrer_id, bonus_amount = db.apply_referral_bonus(user_id)
        if referrer_id:
            try:
                await context.bot.send_message(user_id, f"🎁 تبریک! مبلغ {bonus_amount:,.0f} تومان به عنوان هدیه اولین خرید به کیف پول شما اضافه شد.")
                await context.bot.send_message(referrer_id, f"🎉 یکی از دوستان شما خرید خود را تکمیل کرد و {bonus_amount:,.0f} تومان به کیف پول شما اضافه شد.")
            except (Forbidden, BadRequest):
                pass
        try:
            await msg_loading.delete()
        except BadRequest:
            pass
        from .user_services import show_link_options_menu
        await show_link_options_menu(message, result['uuid'], is_edit=False)
    else:
        db.cancel_purchase_transaction(transaction_id)
        await msg_loading.edit_text("❌ ساخت سرویس ناموفق بود. لطفاً به پشتیبانی اطلاع دهید.")

    context.user_data.clear()
    return ConversationHandler.END