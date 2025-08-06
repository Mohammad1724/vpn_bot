import logging, os, shutil, asyncio, random, sqlite3, io
from datetime import datetime, timedelta, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputFile
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler, MessageHandler, 
                          filters, ContextTypes, ConversationHandler, ApplicationBuilder)
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest

import database as db
import hiddify_api
from config import (BOT_TOKEN, ADMIN_ID, SUPPORT_USERNAME, SUB_DOMAINS, ADMIN_PATH, 
                    PANEL_DOMAIN, SUB_PATH, TRIAL_ENABLED, TRIAL_DAYS, TRIAL_GB)

import qrcode

os.makedirs('backups', exist_ok=True)
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

(ADMIN_MENU, PLAN_MENU, SETTINGS_MENU, BACKUP_MENU, GIFT_MENU, BROADCAST_MENU, USER_MANAGEMENT_MENU,
 PLAN_NAME, PLAN_PRICE, PLAN_DAYS, PLAN_GB,
 SET_CARD_NUMBER, SET_CARD_HOLDER,
 CHARGE_AMOUNT, CHARGE_RECEIPT,
 REDEEM_GIFT,
 RESTORE_UPLOAD, RESTORE_CONFIRM,
 BROADCAST_MESSAGE, BROADCAST_CONFIRM,
 GIFT_AMOUNT, GIFT_COUNT,
 MANAGE_USER_ID, MANAGE_USER_ACTION, MANAGE_USER_AMOUNT,
 BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE,
 GET_CUSTOM_NAME) = range(28)

def get_main_menu_keyboard(user_id):
    user_info = db.get_or_create_user(user_id)
    keyboard = [["🛍️ خرید سرویس", "📋 سرویس‌های من"], ["💰 موجودی و شارژ", "🎁 کد هدیه"]]
    if TRIAL_ENABLED and user_info and not user_info.get('has_used_trial'):
        keyboard.append(["🧪 دریافت سرویس تست رایگان"])
    keyboard.append(["📞 پشتیبانی", " راهنمای اتصال 📚"])
    if user_id == ADMIN_ID: keyboard.append(["👑 ورود به پنل ادمین"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
def get_admin_menu_keyboard():
    keyboard = [["➕ مدیریت پلن‌ها", "📊 آمار ربات"], ["⚙️ تنظیمات", "🎁 مدیریت کد هدیه"], ["📩 ارسال پیام", "💾 پشتیبان‌گیری"], ["👥 مدیریت کاربران"], ["🛑 خاموش کردن ربات", "↩️ خروج از پنل"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def check_expiring_services(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Running daily check for expiring services...")
    expiring_services = db.get_services_expiring_soon(days=3)
    for service in expiring_services:
        try:
            await context.bot.send_message(chat_id=service['user_id'], text=f"📢 یادآوری: سرویس شما با لینک زیر در تاریخ {service['expiry_date']} منقضی خواهد شد.\n\n`{service['sub_link']}`", parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(0.1)
        except (Forbidden, BadRequest): logger.warning(f"Could not send expiry notification to user {service['user_id']}.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = db.get_or_create_user(user_id)
    if user_info and user_info.get('is_banned'):
        await update.message.reply_text("شما از استفاده از این ربات منع شده‌اید."); return ConversationHandler.END
    await update.message.reply_text("👋 به ربات فروش VPN خوش آمدید!", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_or_create_user(update.effective_user.id)
    keyboard = [[InlineKeyboardButton("💳 شارژ حساب", callback_data="start_charge")]]
    await update.message.reply_text(f"💰 موجودی فعلی شما: **{user['balance']:.0f}** تومان", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text(f"جهت ارتباط با پشتیبانی به آیدی زیر پیام ارسال کنید:\n@{SUPPORT_USERNAME}")
async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("راهنمای اتصال به سرویس‌ها:\n\n(اینجا می‌توانید آموزش‌های لازم را قرار دهید)")

async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans()
    if not plans: await update.message.reply_text("متاسفانه در حال حاضر هیچ پلنی برای فروش موجود نیست."); return
    keyboard = [[InlineKeyboardButton(f"{p['name']} - {p['days']} روزه {p['gb']} گیگ - {p['price']:.0f} تومان", callback_data=f"buy_{p['plan_id']}")] for p in plans]
    await update.message.reply_text("لطفا سرویس مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def get_trial_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = db.get_or_create_user(user_id)
    if not TRIAL_ENABLED: await update.message.reply_text("در حال حاضر سرویس تست فعال نمی‌باشد."); return
    if user_info.get('has_used_trial'): await update.message.reply_text("شما قبلاً از سرویس تست رایگان استفاده کرده‌اید."); return
    msg_loading = await update.message.reply_text("در حال ساخت سرویس تست شما... ⏳")
    result = hiddify_api.create_hiddify_user(TRIAL_DAYS, TRIAL_GB, user_id, custom_name="سرویس تست")
    if result and result.get('uuid'):
        db.set_user_trial_used(user_id)
        db.add_active_service(user_id, result['uuid'], result['full_link'], 0, TRIAL_DAYS)
        await show_link_options_with_qr(msg_loading, result['uuid'], result['config_name'], context, is_edit=True)
    else: await msg_loading.edit_text("❌ متاسفانه در ساخت سرویس تست مشکلی پیش آمد. لطفا بعداً تلاش کنید.")

async def list_my_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id; services = db.get_user_services(user_id)
    if not services: await update.message.reply_text("شما در حال حاضر هیچ سرویس فعالی ندارید."); return
    msg = await update.message.reply_text("در حال دریافت اطلاعات سرویس‌های شما... ⏳")
    for service in services:
        info = hiddify_api.get_user_info(service['sub_uuid'])
        if info:
            start_date_str, package_days = info.get('start_date'), info.get('package_days', 0)
            expiry_date_display, is_expired = "N/A", True
            if package_days > 0:
                try:
                    start_date_obj = datetime.now().date() if not start_date_str else datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    expiry_date_obj = start_date_obj + timedelta(days=package_days)
                    expiry_date_display, is_expired = expiry_date_obj.strftime("%Y-%m-%d"), expiry_date_obj < datetime.now().date()
                except (ValueError, TypeError): logger.error(f"Could not parse start_date: {start_date_str}"); is_expired = True
            status, renewal_plan = "🔴 منقضی شده" if is_expired else "🟢 فعال", db.get_plan(service['plan_id'])
            message = (f"🔗 لینک پروفایل: `{service['sub_link']}`\n🗓️ تاریخ انقضا: {expiry_date_display}\n📊 حجم مصرفی: {info.get('current_usage_GB', 0):.2f} / {info.get('usage_limit_GB', 0):.0f} گیگ\n🚦 وضعیت: {status}")
            keyboard = [[InlineKeyboardButton("📋 دریافت لینک‌های اشتراک", callback_data=f"showlinks_{service['sub_uuid']}")]]
            if renewal_plan and not is_expired: keyboard.append([InlineKeyboardButton(f"🔄 تمدید ({renewal_plan['price']:.0f} تومان)", callback_data=f"renew_{service['service_id']}_{renewal_plan['plan_id']}")])
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
        else: await update.message.reply_text(f"خطا در دریافت اطلاعات برای لینک:\n`{service['sub_link']}`", parse_mode=ParseMode.MARKDOWN)
    await msg.delete()

async def gift_code_entry(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("🎁 لطفا کد هدیه خود را وارد کنید:", reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)); return REDEEM_GIFT
async def redeem_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code, user_id = update.message.text.upper(), update.effective_user.id; amount = db.use_gift_code(code, user_id)
    if amount: await update.message.reply_text(f"✅ تبریک! مبلغ {amount:.0f} تومان به کیف پول شما اضافه شد.", reply_markup=get_main_menu_keyboard(user_id))
    else: await update.message.reply_text("❌ کد هدیه نامعتبر یا استفاده شده است.", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

async def charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.message.reply_text("لطفاً مبلغی که قصد واریز آن را دارید به تومان وارد کنید (فقط عدد):", reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)); return CHARGE_AMOUNT
async def charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount <= 1000: raise ValueError
        context.user_data['charge_amount'] = amount
        card_number, card_holder = db.get_setting('card_number'), db.get_setting('card_holder')
        await update.message.reply_text(f"لطفاً مبلغ **{amount:,} تومان** را به شماره کارت زیر واریز نمایید:\n\n`{card_number}`\nبه نام: {card_holder}\n\nسپس از رسید واریزی خود عکس گرفته و آن را ارسال کنید.", parse_mode=ParseMode.MARKDOWN); return CHARGE_RECEIPT
    except ValueError: await update.message.reply_text("لطفا یک عدد صحیح و بیشتر از 1000 تومان وارد کنید."); return CHARGE_AMOUNT
async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, amount = update.effective_user, context.user_data['charge_amount']; receipt_photo = update.message.photo[-1]
    caption = (f"درخواست شارژ جدید 🔔\n\nکاربر: {user.full_name} (@{user.username})\nآیدی عددی: `{user.id}`\nمبلغ درخواستی: **{amount:,} تومان**")
    keyboard = [[InlineKeyboardButton("✅ تایید شارژ", callback_data=f"confirm_charge_{user.id}_{amount}"), InlineKeyboardButton("❌ رد درخواست", callback_data=f"reject_charge_{user.id}")]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=receipt_photo.file_id, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    await update.message.reply_text("✅ رسید شما برای ادمین ارسال شد. لطفاً تا زمان بررسی منتظر بمانید.", reply_markup=get_main_menu_keyboard(user.id))
    context.user_data.clear(); return ConversationHandler.END

async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id, data = query.from_user.id, query.data.split('_'); plan_id = int(data[1])
    plan, user = db.get_plan(plan_id), db.get_or_create_user(user_id)
    if not plan: await query.edit_message_text("❌ این پلن دیگر موجود نیست."); return ConversationHandler.END
    if user['balance'] < plan['price']: await query.edit_message_text(f"موجودی شما کافی نیست!\nموجودی: {user['balance']:.0f} تومان\nقیمت پلن: {plan['price']:.0f} تومان"); return ConversationHandler.END
    context.user_data['plan_to_buy'] = plan_id
    await query.edit_message_text("✅ پلن شما انتخاب شد.\n\nلطفاً یک نام دلخواه برای این سرویس وارد کنید (مثلاً: گوشی شخصی).\nبرای استفاده از نام پیش‌فرض، دستور /skip را ارسال کنید.", reply_markup=None)
    return GET_CUSTOM_NAME
async def get_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    custom_name = update.message.text
    if len(custom_name) > 50: await update.message.reply_text("نام وارد شده بیش از حد طولانی است."); return GET_CUSTOM_NAME
    context.user_data['custom_name'] = custom_name
    await create_service_after_name(update, context)
    return ConversationHandler.END
async def skip_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['custom_name'] = ""
    await create_service_after_name(update, context)
    return ConversationHandler.END
async def create_service_after_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_entity = update.message; user_id = message_entity.chat_id
    plan_id = context.user_data['plan_to_buy']; custom_name = context.user_data.get('custom_name', "")
    plan = db.get_plan(plan_id)
    msg = await message_entity.reply_text("در حال ساخت سرویس شما... ⏳")
    result = hiddify_api.create_hiddify_user(plan['days'], plan['gb'], user_id, custom_name=custom_name)
    if result and result.get('uuid'):
        db.update_balance(user_id, plan['price'], add=False); db.add_active_service(user_id, result['uuid'], result['full_link'], plan['plan_id'], plan['days']); db.log_sale(user_id, plan['plan_id'], plan['price'])
        await show_link_options_with_qr(msg, result['uuid'], result['config_name'], context, is_edit=True)
    else: await msg.edit_text("❌ متاسفانه در ساخت سرویس مشکلی پیش آمد. لطفا به پشتیبانی اطلاع دهید.")
    context.user_data.clear()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id, data = query.from_user.id, query.data.split('_'); action = data[0]
    if action == "showlinks": await show_link_options_with_qr(query.message, data[1], context, is_edit=False)
    elif action == "getlink":
        link_type, user_uuid = data[1], data[2]
        await query.message.delete()
        await show_link_options_with_qr(query.message, user_uuid, context, is_edit=False, link_type=link_type)
    elif action == "renew":
        service_id, plan_id = int(data[1]), int(data[2])
        service, plan, user = db.get_service(service_id), db.get_plan(plan_id), db.get_or_create_user(user_id)
        if not service or not plan: await query.edit_message_text("❌ سرویس یا پلن تمدید نامعتبر است."); return
        if user['balance'] < plan['price']: await query.edit_message_text(f"موجودی برای تمدید کافی نیست! (نیاز به {plan['price']:.0f} تومان)"); return
        await query.edit_message_text("در حال تمدید سرویس... ⏳")
        success = hiddify_api.renew_user_subscription(service['sub_uuid'], plan['days'], plan['gb'])
        if success: db.update_balance(user_id, plan['price'], add=False); db.renew_service(service_id, plan['days']); db.log_sale(user_id, plan_id, plan['price']); await query.edit_message_text("✅ سرویس شما با موفقیت تمدید شد!")
        else: await query.edit_message_text("❌ خطا در تمدید سرویس. لطفا به پشتیبانی اطلاع دهید. (ممکن است پنل شما از این قابلیت پشتیبانی نکند)")
    elif action == "confirm" and data[1] == "charge" and user_id == ADMIN_ID:
        target_user_id, amount = int(data[2]), int(data[3]); db.update_balance(target_user_id, amount, add=True); user_message_sent = False
        try: await context.bot.send_message(chat_id=target_user_id, text=f"حساب شما با موفقیت به مبلغ **{amount:,} تومان** شارژ شد!", parse_mode=ParseMode.MARKDOWN); user_message_sent = True
        except (Forbidden, BadRequest): pass
        admin_feedback = f"✅ با موفقیت مبلغ {amount:,} تومان به حساب کاربر {target_user_id} اضافه شد."
        if not user_message_sent: admin_feedback += "\n\n⚠️ **اخطار:** کاربر ربات را بلاک کرده."
        await query.edit_message_caption(caption=admin_feedback, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
    elif action == "reject" and data[1] == "charge" and user_id == ADMIN_ID:
        target_user_id = int(data[2]); user_message_sent = False
        try: await context.bot.send_message(chat_id=target_user_id, text="متاسفانه درخواست شارژ حساب شما توسط ادمین رد شد."); user_message_sent = True
        except (Forbidden, BadRequest): pass
        admin_feedback = f"❌ درخواست شارژ کاربر {target_user_id} رد شد."
        if not user_message_sent: admin_feedback += "\n\n⚠️ **اخطار:** کاربر ربات را بلاک کرده."
        await query.edit_message_caption(caption=admin_feedback, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
    elif action == "delete" and data[1] == "plan" and user_id == ADMIN_ID: db.delete_plan(int(data[2])); await query.edit_message_text("پلن با موفقیت حذف شد.")
    elif action == "edit" and user_id == ADMIN_ID:
        context.user_data['query_message_id'] = query.message.message_id
        if data[1] == "card" and data[2] == "number": await query.message.reply_text(f"شماره کارت فعلی: {db.get_setting('card_number')}\nشماره کارت جدید را وارد کنید:"); context.user_data['next_state'] = SET_CARD_NUMBER
        elif data[1] == "card" and data[2] == "holder": await query.message.reply_text(f"نام صاحب حساب فعلی: {db.get_setting('card_holder')}\nنام جدید را وارد کنید:"); context.user_data['next_state'] = SET_CARD_HOLDER
    elif action == "confirm" and data[1] == "restore" and user_id == ADMIN_ID:
        restore_path = context.user_data.get('restore_path')
        if not restore_path or not os.path.exists(restore_path): await query.edit_message_text("خطا: فایل پشتیبان یافت نشد."); return
        try: shutil.move(restore_path, db.DB_NAME); await query.edit_message_text("✅ دیتابیس با موفقیت بازیابی شد.\n\n**مهم:** برای اعمال کامل تغییرات، لطفاً سرویس ربات را با دستور زیر ری‌استارت کنید:\n`sudo systemctl restart vpn_bot`", parse_mode=ParseMode.MARKDOWN)
        except Exception as e: await query.edit_message_text(f"خطا در هنگام جایگزینی فایل دیتابیس: {e}")
        context.user_data.clear()
    elif action == "cancel" and data[1] == "restore" and user_id == ADMIN_ID:
        restore_path = context.user_data.get('restore_path')
        if restore_path and os.path.exists(restore_path): os.remove(restore_path)
        await query.edit_message_text("عملیات بازیابی لغو شد."); context.user_data.clear()

async def show_link_options_with_qr(query_or_update, user_uuid, config_name, context, is_edit=True):
    message_entity = query_or_update.message if hasattr(query_or_update, 'message') else query_or_update
    sub_path = SUB_PATH or ADMIN_PATH; sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    base_link = f"https://{sub_domain}/{sub_path}/{user_uuid}"
    final_link = f"{base_link}/sub/?asn=unknown#{config_name}"
    qr_image = qrcode.make(final_link); bio = io.BytesIO(); bio.name = 'qrcode.png'; qr_image.save(bio, 'PNG'); bio.seek(0)
    caption = (f"✅ سرویس شما با موفقیت ساخته شد!\n\nنام کانفیگ: **{config_name.replace('-', ' ')}**\n\nمی‌توانید با اسکن QR کد زیر یا با استفاده از لینک اشتراک، به سرویس متصل شوید.\n\nلینک اشتراک استاندارد شما:\n`{final_link}`")
    if is_edit: await message_entity.delete()
    await context.bot.send_photo(chat_id=message_entity.chat_id, photo=bio, caption=caption, parse_mode=ParseMode.MARKDOWN)

async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("👑 به پنل ادمین خوش آمدید.", reply_markup=get_admin_menu_keyboard()); return ADMIN_MENU
async def exit_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("شما از پنل ادمین خارج شدید.", reply_markup=get_main_menu_keyboard(update.effective_user.id)); return ConversationHandler.END
async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("به منوی اصلی ادمین بازگشتید.", reply_markup=get_admin_menu_keyboard()); return ADMIN_MENU
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_stats(); message = (f"📊 **آمار کلی ربات**\n\n👥 تعداد کل کاربران: {stats['user_count']} نفر\n🛒 تعداد کل فروش‌ها: {stats['sales_count']} عدد\n💳 درآمد کل: {stats['total_revenue']:.0f} تومان")
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
async def plan_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE): keyboard = [["➕ افزودن پلن جدید", "📋 لیست پلن‌ها"], ["بازگشت به منوی ادمین"]]; await update.message.reply_text("بخش مدیریت پلن‌ها", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)); return PLAN_MENU
async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("لطفا نام پلن را وارد کنید:", reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)); return PLAN_NAME
async def plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE): context.user_data['plan_name'] = update.message.text; await update.message.reply_text("نام ثبت شد. قیمت را به تومان وارد کنید:"); return PLAN_PRICE
async def plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: context.user_data['plan_price'] = float(update.message.text); await update.message.reply_text("قیمت ثبت شد. تعداد روزهای اعتبار را وارد کنید:"); return PLAN_DAYS
    except ValueError: await update.message.reply_text("لطفا قیمت را به صورت عدد وارد کنید."); return PLAN_PRICE
async def plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: context.user_data['plan_days'] = int(update.message.text); await update.message.reply_text("تعداد روز ثبت شد. حجم سرویس به گیگابایت را وارد کنید:"); return PLAN_GB
    except ValueError: await update.message.reply_text("لطفا تعداد روز را به صورت عدد وارد کنید."); return PLAN_DAYS
async def plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_gb'] = int(update.message.text)
        db.add_plan(context.user_data['plan_name'], context.user_data['plan_price'], context.user_data['plan_days'], context.user_data['plan_gb'])
        await update.message.reply_text("✅ پلن جدید اضافه شد!", reply_markup=get_admin_menu_keyboard()); context.user_data.clear(); return ADMIN_MENU
    except ValueError: await update.message.reply_text("لطفا حجم را به صورت عدد وارد کنید."); return PLAN_GB
async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans()
    if not plans: await update.message.reply_text("هیچ پلنی تعریف نشده."); return
    for p in plans:
        text = f"🔹 **{p['name']}** (ID: `{p['plan_id']}`)\n   - قیمت: {p['price']:.0f} تومان\n   - مشخصات: {p['days']} روزه / {p['gb']} گیگ"
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_plan_{p['plan_id']}")]]) , parse_mode=ParseMode.MARKDOWN)
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card_number, card_holder = db.get_setting('card_number'), db.get_setting('card_holder')
    text = (f"⚙️ **تنظیمات ربات**\n\nشماره کارت فعلی: `{card_number}`\nصاحب حساب فعلی: `{card_holder}`")
    keyboard = [[InlineKeyboardButton("ویرایش شماره کارت", callback_data="edit_card_number"), InlineKeyboardButton("ویرایش نام صاحب حساب", callback_data="edit_card_holder")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN); return SETTINGS_MENU
async def handle_settings_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    next_state = context.user_data.get('next_state')
    if not next_state: await update.message.reply_text("به منوی اصلی ادمین بازگشتید.", reply_markup=get_admin_menu_keyboard()); return ADMIN_MENU
    if next_state == SET_CARD_NUMBER: db.set_setting('card_number', update.message.text); await update.message.reply_text("✅ شماره کارت به‌روز شد.", reply_markup=get_admin_menu_keyboard())
    elif next_state == SET_CARD_HOLDER: db.set_setting('card_holder', update.message.text); await update.message.reply_text("✅ نام صاحب حساب به‌روز شد.", reply_markup=get_admin_menu_keyboard())
    if 'query_message_id' in context.user_data:
        try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data.pop('query_message_id'))
        except Exception: pass
    context.user_data.clear(); return ADMIN_MENU
async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["ارسال به همه کاربران", "ارسال به کاربر خاص"], ["بازگشت به منوی ادمین"]]; await update.message.reply_text("بخش ارسال پیام", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)); return BROADCAST_MENU
async def broadcast_to_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("لطفا پیام خود را برای ارسال به همه کاربران وارد کنید:", reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)); return BROADCAST_MESSAGE
async def broadcast_to_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message'] = update.message
    await update.message.reply_text(f"آیا از ارسال پیام به همه کاربران مطمئن هستید؟", reply_markup=ReplyKeyboardMarkup([["بله، ارسال کن"], ["خیر، لغو کن"]], resize_keyboard=True)); return BROADCAST_CONFIRM
async def broadcast_to_all_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_to_send = context.user_data['broadcast_message']
    user_ids = db.get_all_user_ids(); sent_count, failed_count = 0, 0
    await update.message.reply_text(f"در حال ارسال پیام به {len(user_ids)} کاربر...", reply_markup=get_admin_menu_keyboard())
    for user_id in user_ids:
        try: await message_to_send.copy(chat_id=user_id); sent_count += 1; await asyncio.sleep(0.1)
        except (Forbidden, BadRequest): failed_count += 1
    await update.message.reply_text(f"✅ پیام همگانی با موفقیت ارسال شد.\n\nتعداد ارسال موفق: {sent_count}\nتعداد ارسال ناموفق: {failed_count}")
    context.user_data.clear(); return ADMIN_MENU
async def broadcast_to_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("لطفا آیدی عددی کاربر هدف را وارد کنید:", reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)); return BROADCAST_TO_USER_ID
async def broadcast_to_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text)
        context.user_data['target_user_id'] = target_id
        await update.message.reply_text("آیدی ثبت شد. حالا پیامی که می‌خواهید برای این کاربر ارسال کنید را وارد نمایید:"); return BROADCAST_TO_USER_MESSAGE
    except ValueError: await update.message.reply_text("لطفا یک آیدی عددی معتبر وارد کنید."); return BROADCAST_TO_USER_ID
async def broadcast_to_user_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = context.user_data['target_user_id']
    message_to_send = update.message
    try:
        await message_to_send.copy(chat_id=target_id)
        await update.message.reply_text("✅ پیام با موفقیت به کاربر ارسال شد.", reply_markup=get_admin_menu_keyboard())
    except (Forbidden, BadRequest): await update.message.reply_text("❌ ارسال پیام ناموفق بود. احتمالا کاربر ربات را بلاک کرده یا آیدی اشتباه است.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear(); return ADMIN_MENU
async def user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا آیدی عددی کاربری که می‌خواهید مدیریت کنید را وارد نمایید:", reply_markup=ReplyKeyboardMarkup([["بازگشت به منوی ادمین"]], resize_keyboard=True)); return MANAGE_USER_ID
async def manage_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_user_id = int(update.message.text)
        user_info = db.get_user(target_user_id)
        if not user_info: await update.message.reply_text("کاربری با این آیدی یافت نشد."); return MANAGE_USER_ID
        context.user_data['target_user_id'] = target_user_id
        ban_text = "آزاد کردن کاربر" if user_info['is_banned'] else "مسدود کردن کاربر"
        keyboard = [["افزایش موجودی", "کاهش موجودی"], [ban_text], ["بازگشت به منوی ادمین"]]
        info_text = f"مدیریت کاربر: `{target_user_id}`\nموجودی: {user_info['balance']:.0f} تومان\nوضعیت: {'مسدود' if user_info['is_banned'] else 'فعال'}"
        await update.message.reply_text(info_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN); return MANAGE_USER_ACTION
    except ValueError: await update.message.reply_text("لطفا یک آیدی عددی معتبر وارد کنید."); return MANAGE_USER_ID
async def manage_user_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    if action == "بازگشت به منوی ادمین": return await back_to_admin_menu(update, context)
    target_user_id = context.user_data.get('target_user_id')
    if not target_user_id: await update.message.reply_text("خطا: کاربر هدف مشخص نیست."); return await back_to_admin_menu(update, context)
    if action == "افزایش موجودی" or action == "کاهش موجودی":
        context.user_data['manage_action'] = action; await update.message.reply_text("لطفا مبلغ مورد نظر را به تومان وارد کنید:"); return MANAGE_USER_AMOUNT
    elif "مسدود" in action or "آزاد" in action:
        user_info = db.get_user(target_user_id); new_ban_status = not user_info['is_banned']
        db.set_user_ban_status(target_user_id, new_ban_status)
        await update.message.reply_text(f"✅ وضعیت کاربر با موفقیت به '{'مسدود' if new_ban_status else 'فعال'}' تغییر کرد.", reply_markup=get_admin_menu_keyboard()); context.user_data.clear(); return ADMIN_MENU
    else: await update.message.reply_text("دستور نامعتبر است. لطفاً از دکمه‌ها استفاده کنید."); return MANAGE_USER_ACTION
async def manage_user_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text); action, target_user_id = context.user_data['manage_action'], context.user_data['target_user_id']
        if action == "افزایش موجودی": db.update_balance(target_user_id, amount, add=True); await update.message.reply_text(f"✅ مبلغ {amount:.0f} تومان به حساب کاربر اضافه شد.")
        elif action == "کاهش موجودی": db.update_balance(target_user_id, amount, add=False); await update.message.reply_text(f"✅ مبلغ {amount:.0f} تومان از حساب کاربر کسر شد.")
        await back_to_admin_menu(update, context); context.user_data.clear(); return ADMIN_MENU
    except ValueError: await update.message.reply_text("لطفا مبلغ را به صورت عدد وارد کنید."); return MANAGE_USER_AMOUNT
async def backup_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE): keyboard = [["📥 دریافت فایل پشتیبان", "📤 بارگذاری فایل پشتیبان"], ["بازگشت به منوی ادمین"]]; await update.message.reply_text("بخش پشتیبان‌گیری و بازیابی.", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)); return BACKUP_MENU
async def send_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    timestamp, backup_filename = datetime.now().strftime("%Y-%m-%d_%H-%M"), f"backup.db"; shutil.copy(db.DB_NAME, backup_filename)
    await update.message.reply_text("در حال آماده‌سازی فایل پشتیبان...")
    try:
        with open(backup_filename, 'rb') as doc: await context.bot.send_document(chat_id=update.effective_user.id, document=doc, caption=f"پشتیبان دیتابیس - {timestamp}")
    except Exception as e: await update.message.reply_text(f"خطا در ارسال فایل: {e}")
    finally: os.remove(backup_filename)
    return BACKUP_MENU
async def restore_start(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("⚠️ **اخطار:** بازیابی دیتابیس تمام اطلاعات فعلی را پاک می‌کند.\nبرای ادامه، فایل دیتابیس (`.db`) خود را ارسال کنید. برای لغو `/cancel` را بزنید.", parse_mode=ParseMode.MARKDOWN); return RESTORE_UPLOAD
def is_valid_sqlite(filepath):
    try: conn = sqlite3.connect(filepath); cursor = conn.cursor(); cursor.execute("SELECT name FROM sqlite_master WHERE type='table';"); cursor.fetchall(); conn.close(); return True
    except sqlite3.DatabaseError: return False
async def restore_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document.file_name.endswith('.db'): await update.message.reply_text("فرمت فایل نامعتبر است. لطفاً یک فایل `.db` ارسال کنید."); return RESTORE_UPLOAD
    file = await document.get_file(); temp_path = os.path.join("backups", f"restore_temp.db"); await file.download_to_drive(temp_path)
    if not is_valid_sqlite(temp_path): await update.message.reply_text("❌ فایل ارسالی یک دیتابیس SQLite معتبر نیست."); os.remove(temp_path); return BACKUP_MENU
    context.user_data['restore_path'] = temp_path
    keyboard = [[InlineKeyboardButton("✅ بله، مطمئنم", callback_data="confirm_restore"), InlineKeyboardButton("❌ خیر، لغو کن", callback_data="cancel_restore")]]
    await update.message.reply_text("**آیا از جایگزینی دیتابیس فعلی کاملاً مطمئن هستید؟ این عمل غیرقابل بازگشت است.**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
async def shutdown_bot(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("ربات در حال خاموش شدن است..."); asyncio.create_task(context.application.shutdown())
async def admin_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu_keyboard()); context.user_data.clear(); return ADMIN_MENU
async def user_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("عملیات لغو شد.", reply_markup=get_main_menu_keyboard(update.effective_user.id)); context.user_data.clear(); return ConversationHandler.END

def main():
    db.init_db()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    job_queue = application.job_queue; job_queue.run_daily(check_expiring_services, time=time(hour=10, minute=0, second=0))
    admin_filter, user_filter = filters.User(user_id=ADMIN_ID), ~filters.User(user_id=ADMIN_ID)
    buy_handler = ConversationHandler(entry_points=[CallbackQueryHandler(buy_start, pattern='^buy_')], states={GET_CUSTOM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_name), CommandHandler('skip', skip_custom_name)]}, fallbacks=[CommandHandler('cancel', user_generic_cancel)])
    gift_handler = ConversationHandler(entry_points=[MessageHandler(filters.Regex('^🎁 کد هدیه$') & user_filter, gift_code_entry)], states={REDEEM_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_gift_code)]}, fallbacks=[CommandHandler('cancel', user_generic_cancel)])
    charge_handler = ConversationHandler(entry_points=[CallbackQueryHandler(charge_start, pattern='^start_charge$')], states={CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, charge_amount_received)], CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_receipt_received)]}, fallbacks=[CommandHandler('cancel', user_generic_cancel)])
    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^👑 ورود به پنل ادمین$') & admin_filter, admin_entry)],
        states={
            ADMIN_MENU: [MessageHandler(filters.Regex('^➕ مدیریت پلن‌ها$'), plan_management_menu), MessageHandler(filters.Regex('^📊 آمار ربات$'), show_stats), MessageHandler(filters.Regex('^⚙️ تنظیمات$'), settings_menu), MessageHandler(filters.Regex('^💾 پشتیبان‌گیری و بازیابی$'), backup_restore_menu), MessageHandler(filters.Regex('^📩 ارسال پیام$'), broadcast_menu), MessageHandler(filters.Regex('^👥 مدیریت کاربران$'), user_management_menu), MessageHandler(filters.Regex('^🛑 خاموش کردن ربات$'), shutdown_bot)],
            PLAN_MENU: [MessageHandler(filters.Regex('^➕ افزودن پلن جدید$'), add_plan_start), MessageHandler(filters.Regex('^📋 لیست پلن‌ها$'), list_plans_admin), MessageHandler(filters.Regex('^بازگشت به منوی ادمین$'), back_to_admin_menu)],
            SETTINGS_MENU: [CallbackQueryHandler(button_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, handle_settings_text), MessageHandler(filters.Regex('^بازگشت به منوی ادمین$'), back_to_admin_menu)],
            BACKUP_MENU: [MessageHandler(filters.Regex('^📥 دریافت فایل پشتیبان$'), send_backup_file), MessageHandler(filters.Regex('^📤 بارگذاری فایل پشتیبان$'), restore_start), MessageHandler(filters.Regex('^بازگشت به منوی ادمین$'), back_to_admin_menu)],
            BROADCAST_MENU: [MessageHandler(filters.Regex('^ارسال به همه کاربران$'), broadcast_to_all_start), MessageHandler(filters.Regex('^ارسال به کاربر خاص$'), broadcast_to_user_start), MessageHandler(filters.Regex('^بازگشت به منوی ادمین$'), back_to_admin_menu)],
            USER_MANAGEMENT_MENU: [MessageHandler(filters.Regex('^بازگشت به منوی ادمین$'), back_to_admin_menu), MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_id_received)],
            PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_name_received)], PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_price_received)],
            PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_days_received)], PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_gb_received)],
            RESTORE_UPLOAD: [MessageHandler(filters.Document.FileExtension("db"), restore_receive_file)], RESTORE_CONFIRM: [CallbackQueryHandler(button_handler)],
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_to_all_confirm)],
            BROADCAST_CONFIRM: [MessageHandler(filters.Regex('^بله، ارسال کن$'), broadcast_to_all_send), MessageHandler(filters.Regex('^خیر، لغو کن$'), back_to_admin_menu)],
            BROADCAST_TO_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_to_user_id_received)],
            BROADCAST_TO_USER_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_to_user_message_received)],
            MANAGE_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_id_received)],
            MANAGE_USER_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_action_handler)],
            MANAGE_USER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_amount_received)],
        }, fallbacks=[MessageHandler(filters.Regex('^↩️ خروج از پنل$'), exit_admin_panel), CommandHandler('cancel', admin_generic_cancel)]
    )
    application.add_handler(admin_conv); application.add_handler(gift_handler); application.add_handler(charge_handler); application.add_handler(buy_handler)
    application.add_handler(CommandHandler("start", start)); application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$') & user_filter, buy_service_list))
    application.add_handler(MessageHandler(filters.Regex('^📋 سرویس‌های من$') & user_filter, list_my_services))
    application.add_handler(MessageHandler(filters.Regex('^💰 موجودی و شارژ$') & user_filter, show_balance))
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$') & user_filter, show_support))
    application.add_handler(MessageHandler(filters.Regex('^ راهنمای اتصال 📚$') & user_filter, show_guide))
    application.add_handler(MessageHandler(filters.Regex('^🧪 دریافت سرویس تست رایگان$') & user_filter, get_trial_service))
    
    print("Ultimate Bot is running...")
    application.run_polling()

if __name__ == "__main__": main()