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
            context, user_id, username, plan, custom_name
        )
        
        if not new_uuid:
            raise RuntimeError("Failed to create service in panel")
        
        # نهایی کردن تراکنش در پایگاه داده
        db.finalize_purchase_transaction(txn_id, new_uuid, sub_link, custom_name)
        
        # اعمال کد تخفیف در صورت استفاده
        if promo_code:
            db.mark_promo_code_as_used(user_id, promo_code)
        
        # ارسال اطلاعات سرویس به کاربر
        await _send_service_info_to_user(context, user_id, new_uuid, custom_name)
        
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

async def _create_service_in_panel(context, user_id, username, plan, custom_name):
    """ایجاد سرویس در پنل هیدیفای"""
    gb_i = int(plan['gb'])
    default_name = "سرویس نامحدود" if gb_i == 0 else f"سرویس {utils.to_persian_digits(str(gb_i))} گیگ"
    final_name = custom_name or default_name

    note = f"tg:@{username}|id:{user_id}" if username else f"tg:id:{user_id}"

    provision = await hiddify_api.create_hiddify_user(
        plan_days=plan['days'],
        plan_gb=float(plan['gb']),
        user_telegram_id=note,
        custom_name=final_name
    )
    
    if not provision or not provision.get("uuid"):
        return None, None
        
    return provision["uuid"], provision.get('full_link', '')

async def _send_service_info_to_user(context, user_id, new_uuid, custom_name):
    """ارسال اطلاعات سرویس به کاربر"""
    new_service_record = db.get_service_by_uuid(new_uuid)
    user_data = await hiddify_api.get_user_info(new_uuid)
    
    if user_data:
        sub_url = utils.build_subscription_url(new_uuid)
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