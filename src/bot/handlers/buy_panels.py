# filename: bot/handlers/buy_panels.py
# -*- coding: utf-8 -*-

import logging
from typing import List

from telegram import Update, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.ui import btn, nav_row, markup
from bot import panels as pnl
from bot.handlers import buy as buy_h

logger = logging.getLogger(__name__)


def _chunk(lst: List, n: int) -> List[List]:
    return [lst[i:i + n] for i in range(0, len(lst), n)]


async def show_panel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش منوی انتخاب پنل/لوکیشن قبل از شروع فرآیند خرید.
    - اگر فقط یک پنل تعریف شده باشد، همان را انتخاب کرده و مستقیم به لیست خرید می‌رویم.
    - اگر چند پنل باشد، دکمه‌های انتخاب نمایش داده می‌شود.
    """
    panels = pnl.load_panels()
    if not panels:
        # هیچ پنلی تعریف نشده؛ ادامه با مسیر قدیمی
        logger.warning("No panels configured; falling back to old buy flow.")
        if update.callback_query:
            await buy_h.buy_service_list(update, context)
        else:
            await buy_h.buy_service_list(update, context)
        return

    if len(panels) == 1:
        # به صورت خودکار همان پنل را انتخاب کن و ادامه بده
        context.user_data['selected_panel_id'] = panels[0].get("id")
        if update.callback_query:
            await buy_h.buy_service_list(update, context)
        else:
            await buy_h.buy_service_list(update, context)
        return

    # چند پنل داریم: منو را بساز
    buttons = [btn(str(p.get("name") or p.get("id") or "Panel"), f"buy_select_panel_{p.get('id')}") for p in panels]
    rows = _chunk(buttons, 2)
    rows.append(nav_row(home_cb="home_menu"))

    text = "🌍 لطفاً لوکیشن/پنل موردنظر برای خرید را انتخاب کنید:"
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        try:
            await q.message.delete()
        except BadRequest:
            pass
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=markup(rows))
    else:
        await update.effective_message.reply_text(text=text, reply_markup=markup(rows))


async def choose_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ثبت انتخاب پنل در user_data و ورود به فرآیند خرید.
    """
    q = update.callback_query
    await q.answer()

    try:
        panel_id = q.data.split("_")[-1]
    except Exception:
        panel_id = None

    if not panel_id or not pnl.find_panel_by_id(panel_id):
        await q.answer("پنل انتخاب‌شده نامعتبر است.", show_alert=True)
        return

    context.user_data['selected_panel_id'] = panel_id

    try:
        await q.message.delete()
    except BadRequest:
        pass

    # ورود به لیست خرید (همان هندلر فعلی شما)
    await buy_h.buy_service_list(update, context)