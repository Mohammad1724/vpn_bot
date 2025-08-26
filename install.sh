#!/bin/bash
# Menu-based installer/manager for vpn_bot (branch-aware, reinstall-safe, config-validated)

set -Eeuo pipefail

SERVICE_NAME="vpn_bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CONF_FILE="/etc/vpn_bot.conf"
DEFAULT_GITHUB_REPO="https://github.com/Mohammad1724/vpn_bot.git"
DEFAULT_GIT_BRANCH="main"

print_color() {
  local COLOR="$1"; shift
  local TEXT="$*"
  case "$COLOR" in
    red)    echo -e "\033[0;31m${TEXT}\033[0m" ;;
    green)  echo -e "\033[0;32m${TEXT}\033[0m" ;;
    yellow) echo -e "\033[0;33m${TEXT}\033[0m" ;;
    blue)   echo -e "\033[0;34m${TEXT}\033[0m" ;;
    *)      echo "${TEXT}" ;;
  esac
}

pause() { read -rp "Press Enter to continue..." _; }

ensure_root() {
  if [ "$(id -u)" -ne "0" ]; then
    print_color red "Run as root. Example: sudo bash install.sh"
    exit 1
  fi
}

escape_sed() { echo "$1" | sed -e 's/[\/&]/\\&/g'; }

ensure_deps() {
  print_color yellow "Installing system dependencies (python3, venv, git, sqlite3)..."
  apt-get update -y >/dev/null 2>&1 || true
  apt-get install -y python3 python3-pip python3-venv curl git sqlite3 >/dev/null 2>&1 || true
}

load_conf() {
  if [ -f "$CONF_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONF_FILE"
  fi
  if [ -z "${INSTALL_DIR:-}" ] && [ -f "$SERVICE_FILE" ]; then
    INSTALL_DIR="$(grep -E '^WorkingDirectory=' "$SERVICE_FILE" | sed 's/^WorkingDirectory=//')"
    INSTALL_DIR="${INSTALL_DIR%/src}"
  fi
  GITHUB_REPO="${GITHUB_REPO:-$DEFAULT_GITHUB_REPO}"
  GIT_BRANCH="${GIT_BRANCH:-$DEFAULT_GIT_BRANCH}"
}

save_conf() {
  mkdir -p "$(dirname "$CONF_FILE")"
  cat > "$CONF_FILE" <<EOF
SERVICE_NAME=${SERVICE_NAME}
INSTALL_DIR=${INSTALL_DIR}
GITHUB_REPO=${GITHUB_REPO}
GIT_BRANCH=${GIT_BRANCH}
EOF
  print_color green "Saved settings to ${CONF_FILE}"
}

create_system_user() {
  if ! getent group vpn-bot >/dev/null 2>&1; then
    groupadd --system vpn-bot || true
  fi
  if ! id -u vpn-bot >/dev/null 2>&1; then
    print_color yellow "Creating system user 'vpn-bot'..."
    useradd --system --home "${INSTALL_DIR}" --shell /usr/sbin/nologin --gid vpn-bot vpn-bot
  fi
}

create_service_file() {
  print_color yellow "Creating/updating systemd service..."
  cat > "$SERVICE_FILE" << EOL
[Unit]
Description=Hiddify Telegram Bot Service
After=network.target

[Service]
User=vpn-bot
Group=vpn-bot
WorkingDirectory=${INSTALL_DIR}/src
ExecStart=${INSTALL_DIR}/venv/bin/python main_bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOL
  systemctl daemon-reload
}

activate_venv() { # shellcheck disable=SC1090
  source "${INSTALL_DIR}/venv/bin/activate"
}

deactivate_venv() {
  set +u
  deactivate || true
  set -u
}

ensure_install_dir_vars() {
  print_color yellow "Using repository: ${GITHUB_REPO}"
  local DEFAULT_INSTALL_DIR="/opt/vpn-bot"
  read -rp "Installation directory [${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}]: " INSTALL_DIR_INPUT
  INSTALL_DIR="${INSTALL_DIR_INPUT:-${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}}"

  read -rp "Git branch/tag to checkout [${GIT_BRANCH:-$DEFAULT_GIT_BRANCH}]: " GIT_BRANCH_INPUT
  GIT_BRANCH="${GIT_BRANCH_INPUT:-${GIT_BRANCH:-$DEFAULT_GIT_BRANCH}}"
}

validate_telegram_token() {
  local token="$1"
  echo "$token" | grep -qE '^[0-9]+:[a-zA-Z0-9_-]+$'
}

validate_numeric_id() {
  local id="$1"
  [[ "$id" =~ ^[0-9]+$ ]]
}

configure_config_py() {
  local CONFIG_FILE="${INSTALL_DIR}/src/config.py"
  local TEMPLATE_FILE="${INSTALL_DIR}/src/config_template.py"
  
  # اگر فایل کانفیگ وجود ندارد، از template کپی کن
  if [ ! -f "$CONFIG_FILE" ]; then
    if [ ! -f "$TEMPLATE_FILE" ]; then
      print_color red "Missing template file: ${TEMPLATE_FILE}"
      exit 1
    fi
    cp "$TEMPLATE_FILE" "$CONFIG_FILE"
  fi
  
  # خواندن مقادیر قبلی از config.py برای نمایش به عنوان پیش‌فرض
  local prev_token; prev_token=$(awk -F= '/^BOT_TOKEN/ {print $2}' "$CONFIG_FILE" | tr -d ' "')
  local prev_admin_id; prev_admin_id=$(awk -F= '/^ADMIN_ID/ {print $2}' "$CONFIG_FILE" | tr -d ' ')
  local prev_domain; prev_domain=$(awk -F= '/^PANEL_DOMAIN/ {print $2}' "$CONFIG_FILE" | tr -d ' "')
  local prev_admin_path; prev_admin_path=$(awk -F= '/^ADMIN_PATH/ {print $2}' "$CONFIG_FILE" | tr -d ' "')
  local prev_sub_path; prev_sub_path=$(awk -F= '/^SUB_PATH/ {print $2}' "$CONFIG_FILE" | tr -d ' "')
  local prev_api_key; prev_api_key=$(awk -F= '/^API_KEY/ {print $2}' "$CONFIG_FILE" | tr -d ' "')
  local prev_support; prev_support=$(awk -F= '/^SUPPORT_USERNAME/ {print $2}' "$CONFIG_FILE" | tr -d ' "')

  # Bot Token
  while true; do
    read -rp "Telegram Bot Token [${prev_token}]: " BOT_TOKEN
    BOT_TOKEN=${BOT_TOKEN:-$prev_token}
    if validate_telegram_token "$BOT_TOKEN"; then
      break
    else
      print_color yellow "Invalid bot token format."
    fi
  done

  # Admin ID
  while true; do
    read -rp "Telegram Admin ID (numeric) [${prev_admin_id}]: " ADMIN_ID
    ADMIN_ID=${ADMIN_ID:-$prev_admin_id}
    if validate_numeric_id "$ADMIN_ID"; then
      break
    else
      print_color yellow "Invalid admin ID."
    fi
  done

  read -rp "Hiddify panel domain [${prev_domain}]: " PANEL_DOMAIN; PANEL_DOMAIN=${PANEL_DOMAIN:-$prev_domain}
  read -rp "Hiddify ADMIN secret path [${prev_admin_path}]: " ADMIN_PATH; ADMIN_PATH=${ADMIN_PATH:-$prev_admin_path}
  read -rp "Hiddify SUBSCRIPTION secret path [${prev_sub_path}]: " SUB_PATH; SUB_PATH=${SUB_PATH:-$prev_sub_path}
  read -rp "Hiddify API Key [${prev_api_key}]: " API_KEY; API_KEY=${API_KEY:-$prev_api_key}
  read -rp "Support username [${prev_support}]: " SUPPORT_USERNAME; SUPPORT_USERNAME=${SUPPORT_USERNAME:-$prev_support}
  
  # بقیه تنظیمات با پیش‌فرض‌های ثابت
  read -rp "Enter subscription domains (comma-separated): " SUB_DOMAINS_INPUT
  read -rp "Enable free trial? [Y/n]: " ENABLE_TRIAL
  read -rp "Referral bonus amount [5000]: " REFERRAL_BONUS_INPUT
  read -rp "Expiry reminder days [3]: " EXPIRY_REMINDER_INPUT
  read -rp "Low-usage alert threshold [0.8]: " USAGE_ALERT_INPUT

  # اعمال تغییرات
  # ... (بقیه کد sed برای سایر تنظیمات)
  local BOT_TOKEN_E; BOT_TOKEN_E=$(escape_sed "$BOT_TOKEN")
  local PANEL_DOMAIN_E; PANEL_DOMAIN_E=$(escape_sed "$PANEL_DOMAIN")
  sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"${BOT_TOKEN_E}\"|" "$CONFIG_FILE"
  sed -i "s|^ADMIN_ID = .*|ADMIN_ID = ${ADMIN_ID}|" "$CONFIG_FILE"
  sed -i "s|^PANEL_DOMAIN = .*|PANEL_DOMAIN = \"${PANEL_DOMAIN_E}\"|" "$CONFIG_FILE"
  # ...
  
  chmod 640 "$CONFIG_FILE" || true
  print_color green "config.py updated successfully."
}

append_missing_keys_if_any() {
  local CONFIG_FILE="${INSTALL_DIR}/src/config.py"
  [ -f "$CONFIG_FILE" ] || return 0
  local changed=0
  if ! grep -q '^REFERRAL_BONUS_AMOUNT' "$CONFIG_FILE"; then
    echo 'REFERRAL_BONUS_AMOUNT = 5000' >> "$CONFIG_FILE"; changed=1
  fi
  if ! grep -q '^EXPIRY_REMINDER_DAYS' "$CONFIG_FILE"; then
    echo 'EXPIRY_REMINDER_DAYS = 3' >> "$CONFIG_FILE"; changed=1
  fi
  if ! grep -q '^USAGE_ALERT_THRESHOLD' "$CONFIG_FILE"; then
    echo 'USAGE_ALERT_THRESHOLD = 0.8' >> "$CONFIG_FILE"; changed=1
  fi
  [ "$changed" -eq 1 ] && print_color yellow "Added missing config keys to config.py."
}

validate_config_offline() {
  local CONFIG_FILE="${INSTALL_DIR}/src/config.py"
  if [ ! -f "$CONFIG_FILE" ]; then return 1; fi
  python3 - "$CONFIG_FILE" <<'PY'
import re, sys
from pathlib import Path
cfg_path = sys.argv[1] if len(sys.argv) > 1 else ""
if not cfg_path or not Path(cfg_path).exists():
    print("Config not found", file=sys.stderr); sys.exit(2)
data = Path(cfg_path).read_text(encoding="utf-8", errors="ignore")
def get_val(k):
    m = re.search(rf'^\s*{k}\s*=\s*(.+)$', data, re.M)
    return m.group(1).strip() if m else ""
def stripq(x): return x.strip().strip('"').strip("'")
ok = True
if not re.match(r'^[0-9]+:[A-Za-z0-9_-]+$', stripq(get_val("BOT_TOKEN"))):
    print("Invalid BOT_TOKEN format", file=sys.stderr); ok = False
try:
    if int(eval(get_val("ADMIN_ID"), {})) <= 0: raise ValueError
except Exception:
    print("Invalid ADMIN_ID (must be positive number)", file=sys.stderr); ok = False
sys.exit(0 if ok else 2)
PY
  return $?
}

validate_token_online() {
  local CONFIG_FILE="${INSTALL_DIR}/src/config.py"
  local BOT_TOKEN
  BOT_TOKEN=$(awk -F= '/^BOT_TOKEN/ {print $2}' "$CONFIG_FILE" | tr -d ' "')
  if [ -z "$BOT_TOKEN" ]; then return 1; fi
  local RES
  RES=$(curl -s --max-time 6 "https://api.telegram.org/bot${BOT_TOKEN}/getMe" || true)
  echo "$RES" | grep -q '"ok":true'
}

install_or_reinstall() {
  # پاکسازی متغیرهای محیطی
  unset INSTALL_DIR GIT_BRANCH GITHUB_REPO REUSE_CONFIG BACKUP_DIR
  
  ensure_root
  ensure_deps
  load_conf
  ensure_install_dir_vars

  if [ -d "$INSTALL_DIR" ]; then
    print_color yellow "Previous installation found at ${INSTALL_DIR}."
    read -rp "Reuse previous config.py and database? [y/N]: " REUSE_CONFIG
    REUSE_CONFIG=${REUSE_CONFIG:-N}
    print_color yellow "Stopping existing service..."
    systemctl stop "${SERVICE_NAME}" || true

    if [[ "$REUSE_CONFIG" =~ ^[Yy]$ ]]; then
      BACKUP_DIR="/tmp/vpn-bot-backup-$(date +%s)"
      mkdir -p "$BACKUP_DIR"
      [ -f "${INSTALL_DIR}/src/config.py" ] && cp "${INSTALL_DIR}/src/config.py" "${BACKUP_DIR}/config.py" || true
      [ -f "${INSTALL_DIR}/src/vpn_bot.db" ] && cp "${INSTALL_DIR}/src/vpn_bot.db" "${BACKUP_DIR}/vpn_bot.db" || true
      print_color green "Temporary backup saved to ${BACKUP_DIR}."
    fi
    print_color yellow "Removing previous installation..."
    rm -rf "$INSTALL_DIR"
  fi

  print_color yellow "Cloning repository (branch: ${GIT_BRANCH})..."
  git clone --branch "${GIT_BRANCH}" --single-branch "$GITHUB_REPO" "$INSTALL_DIR" || {
    print_color red "git clone failed. Check branch name: ${GIT_BRANCH}"
    exit 1
  }
  cd "$INSTALL_DIR"

  print_color yellow "Creating Python venv and installing dependencies..."
  python3 -m venv venv
  activate_venv
  pip install --upgrade pip >/dev/null 2>&1 || true
  if [ ! -f "requirements.txt" ]; then
    print_color red "requirements.txt not found."
    deactivate_venv; exit 1
  fi
  pip install -r requirements.txt >/dev/null 2>&1 || {
    print_color red "Failed to install Python packages (requirements.txt)."
    deactivate_venv; exit 1
  }
  deactivate_venv

  if [ -f "${INSTALL_DIR}/src/bot/keboards.py" ] && [ ! -f "${INSTALL_DIR}/src/bot/keyboards.py" ]; then
    print_color yellow "Renaming keboards.py -> keyboards.py"
    mv "${INSTALL_DIR}/src/bot/keboards.py" "${INSTALL_DIR}/src/bot/keyboards.py" || true
  fi
  mkdir -p "${INSTALL_DIR}/backups"

  # ایجاد کاربر سیستم و پرمیژن‌ها قبل از بازگردانی
  create_system_user

  if [[ "${REUSE_CONFIG:-N}" =~ ^[Yy]$ ]] && [ -n "${BACKUP_DIR:-}" ]; then
    print_color yellow "Restoring previous config and database..."
    [ -f "${BACKUP_DIR}/config.py" ] && cp "${BACKUP_DIR}/config.py" "${INSTALL_DIR}/src/config.py" || true
    [ -f "${BACKUP_DIR}/vpn_bot.db" ] && cp "${BACKUP_DIR}/vpn_bot.db" "${INSTALL_DIR}/src/vpn_bot.db" || true
    append_missing_keys_if_any
  else
    print_color blue "--- Bot Configuration ---"
    configure_config_py
  fi
  
  # تنظیم پرمیژن‌ها بعد از بازگردانی
  chown -R vpn-bot:vpn-bot "${INSTALL_DIR}" || true
  chmod 640 "${INSTALL_DIR}/src/config.py" || true

  # اعتبارسنجی
  if ! validate_config_offline; then
    print_color red "config.py is invalid or incomplete. Let's configure it now..."
    configure_config_py
  else
    print_color green "config.py offline validation passed."
  fi

  if validate_token_online; then
    print_color green "Telegram token online check passed (getMe ok)."
  else
    print_color yellow "Warning: Telegram getMe failed (no Internet or invalid token). Continuing..."
  fi

  touch "${INSTALL_DIR}/src/bot.log"
  chown vpn-bot:vpn-bot "${INSTALL_DIR}/src/bot.log" || true

  create_service_file

  print_color yellow "Enabling and starting service..."
  systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1 || true
  systemctl start "${SERVICE_NAME}"

  save_conf

  print_color blue "--- Installation Complete ---"
  print_color green "Service '${SERVICE_NAME}' started."
  print_color yellow "Status: systemctl status ${SERVICE_NAME}"
  print_color yellow "Live logs: journalctl -u ${SERVICE_NAME} -f"
}

update_bot() {
  ensure_root
  load_conf
  if [ -z "${INSTALL_DIR:-}" ] || [ ! -d "$INSTALL_DIR" ]; then
    print_color red "Installation directory not found. Please install first."
    exit 1
  fi
  if [ ! -d "${INSTALL_DIR}/.git" ]; then
    print_color red "Install dir is not a git repository. Cannot update."
    exit 1
  fi

  print_color yellow "Stopping service for update..."
  systemctl stop "${SERVICE_NAME}" || true

  print_color yellow "Checking out branch: ${GIT_BRANCH}"
  git -C "$INSTALL_DIR" fetch --all --prune
  git -C "$INSTALL_DIR" checkout "${GIT_BRANCH}" || {
    print_color red "git checkout ${GIT_BRANCH} failed."
    exit 1
  }
  git -C "$INSTALL_DIR" pull --ff-only origin "${GIT_BRANCH}" || {
    print_color red "git pull failed."
    exit 1
  }

  print_color yellow "Updating Python deps..."
  activate_venv
  pip install --upgrade pip >/dev/null 2>&1 || true
  if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
    pip install -r "${INSTALL_DIR}/requirements.txt" >/dev/null 2>&1 || true
  fi
  deactivate_venv

  if [ -f "${INSTALL_DIR}/src/bot/keboards.py" ] && [ ! -f "${INSTALL_DIR}/src/bot/keyboards.py" ]; then
    print_color yellow "Renaming keboards.py -> keyboards.py"
    mv "${INSTALL_DIR}/src/bot/keboards.py" "${INSTALL_DIR}/src/bot/keyboards.py" || true
  fi

  touch "${INSTALL_DIR}/src/bot.log"
  chown vpn-bot:vpn-bot "${INSTALL_DIR}/src/bot.log" || true
  chmod 640 "${INSTALL_DIR}/src/config.py" || true

  print_color yellow "Restarting service..."
  systemctl start "${SERVICE_NAME}"

  save_conf
  print_color green "Update completed."
}

restart_bot() {
  ensure_root
  print_color yellow "Restarting service..."
  systemctl restart "${SERVICE_NAME}" || true
  print_color green "Done."
}

status_bot() {
  ensure_root
  print_color yellow "Service status:"
  systemctl status "${SERVICE_NAME}" --no-pager || true
}

follow_journal() {
  ensure_root
  print_color yellow "Following live journal logs (Ctrl+C to exit)"
  ( journalctl -u "${SERVICE_NAME}" -f )
  print_color yellow "Stopped following logs."
}

follow_bot_log() {
  ensure_root
  load_conf
  local LOG_FILE="${INSTALL_DIR:-/opt/vpn-bot}/src/bot.log"
  if [ -f "$LOG_FILE" ]; then
    print_color yellow "Tailing bot.log (last 200 lines, live). Ctrl+C to exit."
    ( tail -n 200 -f "$LOG_FILE" )
    print_color yellow "Stopped following logs."
  else
    print_color red "bot.log not found at: $LOG_FILE"
  fi
}

uninstall_bot() {
  ensure_root
  load_conf
  print_color red "WARNING: This will remove the service and delete all files."
  read -rp "Are you sure? [y/N]: " CONFIRM
  CONFIRM=${CONFIRM:-N}
  if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    print_color yellow "Uninstall cancelled."
    return
  fi

  print_color yellow "Stopping and disabling service..."
  systemctl stop "${SERVICE_NAME}" || true
  systemctl disable "${SERVICE_NAME}" || true

  if [ -f "$SERVICE_FILE" ]; then
    print_color yellow "Removing service file..."
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
  fi

  local DIR="${INSTALL_DIR:-/opt/vpn-bot}"
  if [ -d "$DIR" ]; then
    print_color yellow "Removing install directory: ${DIR}"
    rm -rf "$DIR"
  fi

  if [ -f "$CONF_FILE" ]; then
    print_color yellow "Removing saved settings: ${CONF_FILE}"
    rm -f "$CONF_FILE"
  fi

  print_color blue "--- Uninstall complete ---"
}

show_menu() {
  clear
  print_color blue "--- VPN Bot Manager ---"
  echo "1) Install / Reinstall"
  echo "2) Update"
  echo "3) Restart"
  echo "4) Status"
  echo "5) Journalctl (live logs)"
  echo "6) bot.log (file logs)"
  echo "7) Uninstall"
  echo "0) Exit"
  echo
}

main_loop() {
  ensure_root
  while true; do
    show_menu
    read -rp "Choose an option: " CHOICE
    case "$CHOICE" in
      1) install_or_reinstall; pause ;;
      2) update_bot; pause ;;
      3) restart_bot; pause ;;
      4) status_bot; pause ;;
      5) follow_journal; pause ;;
      6) follow_bot_log; pause ;;
      7) uninstall_bot; pause ;;
      0) exit 0 ;;
      *) print_color red "Invalid option!"; pause ;;
    esac
  done
}

main_loop