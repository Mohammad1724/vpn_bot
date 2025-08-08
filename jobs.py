# -*- coding: utf-8 -*-
import logging
import asyncio
from datetime import datetime
import jdatetime

from telegram.ext import ContextTypes
from telegram.error import Forbidden, BadRequest

import database as db
import hiddify_api
from config import EXPIRY_REMINDER_DAYS, USAGE_ALERT_THRESHOLD
from utils import get_service_status_and_expiry

logger = logging.getLogger(__name__)

async def check_low_usage(context: ContextTypes.DEFAULT_TYPE):
    """
    Job to check services with low usage remaining and alert users.
    """
    logger.info("Running job: Checking for low usage services...")
    try:
        all_services = await db.get_all_active_services()
        for service in all_services:
            if service['low_usage_alert_sent']:
                continue
            try:
                info = await hiddify_api.get_user_info(service['sub_uuid'])
                if not info:
                    logger.warning(f"Could not get info for service {service['service_id']} during usage check.")
                    continue

                _, _, is_expired = await get_service_status_and_expiry(info)
                if is_expired:
                    continue

                usage_limit = info.get('usage_limit_GB', 0)
                current_usage = info.get('current_usage_GB', 0)

                if usage_limit > 0 and (current_usage / usage_limit) >= USAGE_ALERT_THRESHOLD:
                    user_id = service['user_id']
                    service_name = f"'{service['name']}'" if service['name'] else ""
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"📢 هشدار اتمام حجم!\n\n"
                            f"کاربر گرامی، بیش از {int(USAGE_ALERT_THRESHOLD * 100)}٪ از حجم سرویس شما {service_name} مصرف شده است.\n"
                            f"({current_usage:.2f} گیگ از {usage_limit:.0f} گیگ)\n\n"
                            "برای جلوگیری از قطعی، پیشنهاد می‌کنیم سرویس خود را تمدید نمایید."
                        )
                    )
                    await db.set_low_usage_alert_sent(service['service_id'])
                    logger.info(f"Sent low usage alert to user {user_id} for service {service['service_id']}.")
                    await asyncio.sleep(0.1) # Avoid hitting rate limits
            except (Forbidden, BadRequest) as e:
                logger.warning(f"Failed to send low usage alert to user {service['user_id']}: {e}")
            except Exception as e:
                logger.error(f"An unexpected error in low usage job for service {service['service_id']}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"A general error occurred in the check_low_usage job: {e}", exc_info=True)


async def check_expiring_services(context: ContextTypes.DEFAULT_TYPE):
    """
    Job to check for services that are expiring soon and remind users.
    """
    logger.info("Running job: Checking for expiring services...")
    try:
        all_services = await db.get_all_active_services()
        for service in all_services:
            try:
                info = await hiddify_api.get_user_info(service['sub_uuid'])
                if not info:
                    continue

                _, expiry_date_str, is_expired = await get_service_status_and_expiry(info)
                if is_expired or expiry_date_str == "N/A":
                    continue

                # Convert Jalali date back to Gregorian to calculate days left
                parts = expiry_date_str.split('/')
                jalali_date = jdatetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
                gregorian_expiry_date = jalali_date.togregorian()

                days_left = (gregorian_expiry_date - datetime.now().date()).days

                if days_left == EXPIRY_REMINDER_DAYS:
                    user_id = service['user_id']
                    service_name = f"'{service['name']}'" if service['name'] else ""

                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⏳ **یادآوری انقضای سرویس**\n\n"
                            f"کاربر گرامی، تنها **{days_left} روز** تا پایان اعتبار سرویس شما {service_name} باقی مانده است.\n\n"
                            f"برای جلوگیری از قطعی، لطفاً سرویس خود را تمدید نمایید."
                        )
                    )
                    logger.info(f"Sent expiry reminder to user {user_id} for service {service['service_id']}.")
                    await asyncio.sleep(0.1) # Avoid hitting rate limits
            except (Forbidden, BadRequest) as e:
                logger.warning(f"Failed to send expiry reminder to user {service['user_id']}: {e}")
            except Exception as e:
                logger.error(f"An unexpected error in expiry reminder job for service {service['service_id']}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"A general error occurred in the check_expiring_services job: {e}", exc_info=True)
