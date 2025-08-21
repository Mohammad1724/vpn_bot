async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    """بهبود مدیریت منابع و خطاها در پشتیبان‌گیری خودکار"""
    logger.info("Job: running auto-backup...")
    
    # تنظیم مسیرهای پشتیبان‌گیری
    base_dir = os.path.dirname(os.path.abspath(db.DB_NAME))
    backup_dir = os.path.join(base_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"auto_backup_{timestamp}.sqlite3"
    backup_path = os.path.join(backup_dir, backup_filename)

    # مدیریت فایل‌های قدیمی پشتیبان
    manage_old_backups(backup_dir)
    
    # مقصد ارسال فایل پشتیبان
    target_chat_id = db.get_setting("backup_target_chat_id") or ADMIN_ID
    
    conn = None
    db_closed = False

    try:
        # اتصال فعلی را موقتاً می‌بندیم
        db.close_db()
        db_closed = True
        
        # پشتیبان‌گیری با روش مناسب
        try:
            # ابتدا تلاش با VACUUM INTO در نسخه‌های جدیدتر SQLite
            with sqlite3.connect(db.DB_NAME) as conn:
                # بررسی نسخه SQLite برای پشتیبانی از VACUUM INTO
                version = sqlite3.sqlite_version_info
                if version >= (3, 27, 0):
                    conn.execute("VACUUM INTO ?", (backup_path,))
                    logger.info(f"Auto-backup with VACUUM INTO successful")
                else:
                    # استفاده از روش backup() برای نسخه‌های قدیمی‌تر
                    with sqlite3.connect(db.DB_NAME) as src, sqlite3.connect(backup_path) as dst:
                        src.backup(dst)
                    logger.info(f"Auto-backup with backup() API successful")
        except Exception as e:
            logger.error(f"SQLite backup methods failed, using file copy: {e}")
            # اگر روش‌های SQLite شکست خورد، از کپی فایل استفاده می‌کنیم
            shutil.copy2(db.DB_NAME, backup_path)
            logger.info(f"Auto-backup with file copy successful")

        # ارسال فایل به مقصد
        with open(backup_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=target_chat_id,
                document=InputFile(f, filename=backup_filename),
                caption=f"پشتیبان خودکار دیتابیس - {timestamp}"
            )
            logger.info(f"Auto-backup sent to chat {target_chat_id}")
            
    except Exception as e:
        logger.error(f"Auto-backup failed: {e}", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=target_chat_id, 
                text=f"⚠️ بکاپ خودکار با خطا مواجه شد:\n{e}"
            )
        except Exception as msg_error:
            logger.error(f"Failed to send error notification: {msg_error}")
    finally:
        # بازیابی اتصال دیتابیس در هر صورت
        if db_closed:
            db.init_db()
        
        # نگهداری پرونده پشتیبان در سرور
        # فایل‌های قدیمی قبلاً مدیریت شده‌اند

def manage_old_backups(backup_dir, max_backups=10):
    """حذف فایل‌های پشتیبان قدیمی برای مدیریت فضای ذخیره‌سازی"""
    try:
        # لیست فایل‌های پشتیبان
        backup_files = [f for f in os.listdir(backup_dir) 
                        if f.startswith('auto_backup_') and f.endswith('.sqlite3')]
        
        # مرتب‌سازی بر اساس تاریخ ایجاد (قدیمی‌ترین ابتدا)
        backup_files.sort(key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
        
        # حذف فایل‌های قدیمی اگر تعداد بیشتر از حد مجاز است
        if len(backup_files) > max_backups:
            for old_file in backup_files[:-max_backups]:
                os.remove(os.path.join(backup_dir, old_file))
                logger.info(f"Removed old backup file: {old_file}")
    except Exception as e:
        logger.error(f"Error managing old backups: {e}")