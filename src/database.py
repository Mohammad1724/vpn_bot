def initiate_purchase_transaction(user_id: int, plan_id: int, final_price: float) -> int | None:
    """آغاز تراکنش خرید با مدیریت تراکنش بهتر"""
    conn = _connect_db()
    cursor = conn.cursor()
    
    try:
        conn.execute("BEGIN TRANSACTION")
        
        # بررسی موجودی کافی
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user_balance = cursor.fetchone()
        
        if not user_balance or user_balance['balance'] < final_price:
            conn.rollback()
            return None
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO transactions (user_id, plan_id, type, amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, plan_id, 'purchase', final_price, 'pending', now_str, now_str)
        )
        txn_id = cursor.lastrowid
        
        # برای اطمینان از ثبت تراکنش قبل از عملیات بعدی
        conn.commit()
        return txn_id
        
    except sqlite3.Error as e:
        logger.error(f"Error initiating purchase: {e}", exc_info=True)
        conn.rollback()
        return None

def finalize_purchase_transaction(transaction_id: int, sub_uuid: str, sub_link: str, custom_name: str):
    """نهایی کردن تراکنش خرید با مدیریت تراکنش بهتر"""
    conn = _connect_db()
    cursor = conn.cursor()
    
    try:
        conn.execute("BEGIN TRANSACTION")
        
        # بررسی وجود و وضعیت تراکنش
        cursor.execute("SELECT * FROM transactions WHERE transaction_id = ? AND status = 'pending'", (transaction_id,))
        txn = cursor.fetchone()
        
        if not txn:
            conn.rollback()
            raise ValueError("Transaction not found or not pending.")
            
        # کسر مبلغ از موجودی کاربر
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (txn['amount'], txn['user_id']))
        
        # ایجاد سرویس فعال
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO active_services (user_id, name, sub_uuid, sub_link, plan_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (txn['user_id'], custom_name, sub_uuid, sub_link, txn['plan_id'], now_str)
        )
        
        # ثبت در سوابق فروش
        cursor.execute(
            "INSERT INTO sales_log (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)",
            (txn['user_id'], txn['plan_id'], txn['amount'], now_str)
        )
        
        # به‌روزرسانی وضعیت تراکنش
        cursor.execute("UPDATE transactions SET status = 'completed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        
        # ثبت تغییرات
        conn.commit()
        logger.info(f"Purchase transaction {transaction_id} successfully finalized")
        
    except Exception as e:
        logger.error(f"Error finalizing purchase {transaction_id}: {e}", exc_info=True)
        conn.rollback()
        raise