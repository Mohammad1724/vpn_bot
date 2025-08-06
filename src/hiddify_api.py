import requests
import json
import uuid
import random
import logging

from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

logger = logging.getLogger(__name__)

api_session = requests.Session()
api_session.headers.update({
    "Hiddify-API-Key": API_KEY,
    "Content-Type": "application/json"
})

def _get_base_url():
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"

def create_hiddify_user(plan_days, plan_gb, user_telegram_id=None, custom_name="", existing_uuid=None):
    if custom_name: user_name = custom_name.replace(" ", "-")
    else: user_name = f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}"
    comment = f"TG ID: {user_telegram_id}" if user_telegram_id else ""
    payload = {"name": user_name, "package_days": int(plan_days), "usage_limit_GB": int(plan_gb), "comment": comment}
    if existing_uuid: payload['uuid'] = existing_uuid
    endpoint = _get_base_url() + "user/"
    try:
        response = api_session.post(endpoint, json=payload, timeout=20)
        response.raise_for_status()
        user_data = response.json(); user_uuid = user_data.get('uuid')
        if not user_uuid: logger.error("Hiddify API create_hiddify_user did not return a UUID."); return None
        sub_path = SUB_PATH or ADMIN_PATH
        sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
        full_link = f"https://{sub_domain}/{sub_path}/{user_uuid}/"
        logger.info(f"Successfully created/recreated Hiddify user '{user_name}' with UUID {user_uuid}")
        return {"full_link": full_link, "uuid": user_uuid}
    except requests.exceptions.RequestException as e: logger.error(f"Hiddify API request failed in create_hiddify_user: {e}"); return None
    except Exception as e: logger.error(f"An unexpected error occurred in create_hiddify_user: {e}"); return None

def get_user_info(user_uuid):
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        response = api_session.get(endpoint, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e: logger.warning(f"Failed to get Hiddify info for UUID {user_uuid}: {e}"); return None
    except Exception as e: logger.error(f"An unexpected error occurred in get_user_info: {e}"); return None

def delete_user(user_uuid):
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        response = api_session.delete(endpoint, timeout=15)
        response.raise_for_status()
        logger.info(f"Successfully deleted user {user_uuid} as part of renewal.")
        return True
    except requests.exceptions.RequestException as e: logger.error(f"Failed to delete user {user_uuid} during renewal process: {e}"); return False

def renew_user_subscription(user_uuid, plan_days, plan_gb):
    try:
        current_info = get_user_info(user_uuid)
        if not current_info: logger.error(f"Renewal failed: Cannot get current info for user {user_uuid}."); return None
        user_name = current_info.get("name", f"user-{user_uuid[:8]}"); user_tg_id = current_info.get("comment", "").replace("TG ID: ", "")
        if not delete_user(user_uuid): return None
        recreation_result = create_hiddify_user(plan_days=plan_days, plan_gb=plan_gb, user_telegram_id=user_tg_id, custom_name=user_name, existing_uuid=user_uuid)
        if not recreation_result: logger.critical(f"CRITICAL: Deleted user {user_uuid} but FAILED to recreate them. Manual intervention required!"); return None
        new_info = get_user_info(user_uuid)
        if new_info: logger.info(f"Successfully renewed user {user_uuid} using Nuke and Recreate strategy."); return new_info
        else: logger.error(f"CRITICAL: Recreated user {user_uuid} but could not fetch final info."); return None
    except Exception as e: logger.error(f"An unexpected error occurred in the renew_user_subscription (Nuke & Recreate) process: {e}"); return None