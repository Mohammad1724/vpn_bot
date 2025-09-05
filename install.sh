#!/bin/bash
# Menu-based installer/manager for vpn_bot

set -Eeuo pipefail

SERVICE_NAME="vpn_bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CONF_FILE="/etc/vpn_bot.conf"
DEFAULT_GITHUB_REPO="https://github.com/Mohammad1724/vpn_bot.git"

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
  # خروجی نمایش داده می‌شود تا کاربر پیشرفت را ببیند
  apt-get update -y || print_color red "apt-get update failed."
  apt-get install -y python3 python3-pip python3-venv curl git sqlite3 || print_color red "apt-get install failed."
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
}

save_conf() {
  mkdir -p "$(dirname "$CONF_FILE")"
  cat > "$CONF_FILE" <<EOF
SERVICE_NAME=${SERVICE_NAME}
INSTALL_DIR=${INSTALL_DIR}
GITHUB_REPO=${GITHUB_REPO}
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
  GITHUB_REPO="${GITHUB_REPO:-$DEFAULT_GITHUB_REPO}"
  print_color yellow "Using repository: ${GITHUB_REPO}"
  local DEFAULT_INSTALL_DIR="/opt/vpn-bot"
  read -rp "Installation directory [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR_INPUT
  INSTALL_DIR="${INSTALL_DIR_INPUT:-$DEFAULT_INSTALL_DIR}"
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
  if [ ! -f "$TEMPLATE_FILE" ]; then
    print_color red "Missing template file: ${TEMPLATE_FILE}"
    exit 1
  fi
  cp "$TEMPLATE_FILE" "$CONFIG_FILE"

  while true; do
    read -rp "Telegram Bot Token: " BOT_TOKEN
    if validate_telegram_token "$BOT_TOKEN"; then
      break
    else
      print_color yellow "Invalid bot token format."
    fi
  done

  while true; do
    read -rp "Telegram Admin ID (numeric): " ADMIN_ID
    if validate_numeric_id "$ADMIN_ID"; then
      break
    else
      print_color yellow "Invalid admin ID. Must be a number."
    fi
  done

  read -rp "Hiddify panel domain (e.g., mypanel.com): " PANEL_DOMAIN
  read -rp "Hiddify ADMIN secret path: " ADMIN_PATH
  read -rp "Hiddify SUBSCRIPTION secret path (can be the same): " SUB_PATH
  read -rp "Hiddify API Key: " API_KEY
  read -rp "Support username (without @): " SUPPORT_USERNAME

  echo
  print_color yellow "Enter subscription domains comma-separated (or leave empty):"
  read -rp "Subscription Domains: " SUB_DOMAINS_INPUT
  local PYTHON_LIST_FORMAT="[]"
  if [ -n "$SUB_DOMAINS_INPUT" ]; then
    PYTHON_LIST_FORMAT="[\"$(echo "$SUB_DOMAINS_INPUT" | sed 's/,/\", \"/g')\"]"
  fi

  echo
  print_color blue "--- Free Trial ---"
  read -rp "Enable free trial? [Y/n]: " ENABLE_TRIAL
  ENABLE_TRIAL=${ENABLE_TRIAL:-Y}
  local TRIAL_ENABLED_VAL="False"
  local TRIAL_DAYS_VAL=0
  local TRIAL_GB_VAL=0
  if [[ "$ENABLE_TRIAL" =~ ^[Yy]$ ]]; then
    TRIAL_ENABLED_VAL="True"
    read -rp "Trial duration (days) [1]: " TRIAL_DAYS_INPUT
    TRIAL_DAYS_VAL=${TRIAL_DAYS_INPUT:-1}
    read -rp "Trial data limit (GB) [1]: " TRIAL_GB_INPUT
    TRIAL_GB_VAL=${TRIAL_GB_INPUT:-1}
  fi

  echo
  print_color blue "--- Referral & Reminders ---"
  read -rp "Referral bonus amount (Toman) [5000]: " REFERRAL_BONUS_INPUT
  local REFERRAL_BONUS_AMOUNT="${REFERRAL_BONUS_INPUT:-5000}"
  read -rp "Expiry reminder days before end [3]: " EXPIRY_REMINDER_INPUT
  local EXPIRY_REMINDER_DAYS="${EXPIRY_REMINDER_INPUT:-3}"

  echo
  print_color blue "--- Usage Alert ---"
  read -rp "Low-usage alert threshold (0.0 - 1.0) [0.8]: " USAGE_ALERT_INPUT
  local USAGE_ALERT_THRESHOLD="${USAGE_ALERT_INPUT:-0.8}"

  local BOT_TOKEN_E; BOT_TOKEN_E=$(escape_sed "$BOT_TOKEN")
  local PANEL_DOMAIN_E; PANEL_DOMAIN_E=$(escape_sed "$PANEL_DOMAIN")
  local ADMIN_PATH_E; ADMIN_PATH_E=$(escape_sed "$ADMIN_PATH")
  local SUB_PATH_E; SUB_PATH_E=$(escape_sed "$SUB_PATH")
  local API_KEY_E; API_KEY_E=$(escape_sed "$API_KEY")
  local SUPPORT_USERNAME_E; SUPPORT_USERNAME_E=$(escape_sed "$SUPPORT_USERNAME")

  sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"${BOT_TOKEN_E}\"|" "$CONFIG_FILE"
  sed -i "s|^ADMIN_ID = .*|ADMIN_ID = ${ADMIN_ID}|" "$CONFIG_FILE"
  sed -i "s|^PANEL_DOMAIN = .*|PANEL_DOMAIN = \"${PANEL_DOMAIN_E}\"|" "$CONFIG_FILE"
  sed -i "s|^ADMIN_PATH = .*|ADMIN_PATH = \"${ADMIN_PATH_E}\"|" "$CONFIG_FILE"
  sed -i "s|^SUB_PATH = .*|SUB_PATH = \"${SUB_PATH_E}\"|" "$CONFIG_FILE"
  sed -i "s|^API_KEY = .*|API_KEY = \"${API_KEY_E}\"|" "$CONFIG_FILE"
  sed -i "s|^SUPPORT_USERNAME = .*|SUPPORT_USERNAME = \"${SUPPORT_USERNAME_E}\"|" "$CONFIG_FILE"
  sed -i "s|^SUB_DOMAINS = .*|SUB_DOMAINS = ${PYTHON_LIST_FORMAT}|" "$CONFIG_FILE"
  sed -i "s|^TRIAL_ENABLED = .*|TRIAL_ENABLED = ${TRIAL_ENABLED_VAL}|" "$CONFIG_FILE"
  sed -i "s|^TRIAL_DAYS = .*|TRIAL_DAYS = ${TRIAL_DAYS_VAL}|" "$CONFIG_FILE"
  sed -i "s|^TRIAL_GB = .*|TRIAL_GB = ${TRIAL_GB_VAL}|" "$CONFIG_FILE"
  sed -i "s|^REFERRAL_BONUS_AMOUNT = .*|REFERRAL_BONUS_AMOUNT = ${REFERRAL_BONUS_AMOUNT}|" "$CONFIG_FILE"
  sed -i "s|^EXPIRY_REMINDER_DAYS = .*|EXPIRY_REMINDER_DAYS = ${EXPIRY_REMINDER_DAYS}|" "$CONFIG_FILE"
  sed -i "s|^USAGE_ALERT_THRESHOLD = .*|USAGE_ALERT_THRESHOLD = ${USAGE_ALERT_THRESHOLD}|" "$CONFIG_FILE"

  echo
  print_color blue "--- Subconverter (Unified Link) ---"
  read -rp "Enable Subconverter unified link? [y/N]: " EN_SUB
  EN_SUB=${EN_SUB:-N}
  local SUBCONVERTER_ENABLED_VAL="False"
  local SUBCONVERTER_URL_VAL="http://127.0.0.1:25500"
  local SUBCONVERTER_DEFAULT_TARGET_VAL="v2ray"
  local SUBCONVERTER_EXTRA_SERVERS_VAL="[]"

  if [[ "$EN_SUB" =~ ^[Yy]$ ]]; then
    SUBCONVERTER_ENABLED_VAL="True"
    read -rp "Subconverter URL [http://127.0.0.1:25500]: " SUBC_URL_IN
    SUBCONVERTER_URL_VAL="${SUBC_URL_IN:-http://127.0.0.1:25500}"
    read -rp "Default target (v2ray|clash|clashmeta|singbox) [v2ray]: " SUBC_TGT_IN
    SUBCONVERTER_DEFAULT_TARGET_VAL="${SUBC_TGT_IN:-v2ray}"
    echo "Enter extra server names to include in unified link (comma-separated):"
    read -rp "Extra servers: " SUBC_EXTRA_IN
    if [ -n "$SUBC_EXTRA_IN" ]; then
      SUBCONVERTER_EXTRA_SERVERS_VAL="[\"$(echo "$SUBC_EXTRA_IN" | sed 's/,/\", \"/g')\"]"
    fi
  fi

  local SUBC_URL_E; SUBC_URL_E=$(escape_sed "$SUBCONVERTER_URL_VAL")
  local SUBC_TGT_E; SUBC_TGT_E=$(escape_sed "$SUBCONVERTER_DEFAULT_TARGET_VAL")

  sed -i "s|^SUBCONVERTER_ENABLED = .*|SUBCONVERTER_ENABLED = ${SUBCONVERTER_ENABLED_VAL}|" "$CONFIG_FILE"
  sed -i "s|^SUBCONVERTER_URL = .*|SUBCONVERTER_URL = \"${SUBC_URL_E}\"|" "$CONFIG_FILE"
  sed -i "s|^SUBCONVERTER_DEFAULT_TARGET = .*|SUBCONVERTER_DEFAULT_TARGET = \"${SUBC_TGT_E}\"|" "$CONFIG_FILE"
  sed -i "s|^SUBCONVERTER_EXTRA_SERVERS = .*|SUBCONVERTER_EXTRA_SERVERS = ${SUBCONVERTER_EXTRA_SERVERS_VAL}|" "$CONFIG_FILE"

  chmod 640 "$CONFIG_FILE" || true
  print_color green "config.py created/updated successfully."
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
  if ! grep -q '^SUBCONVERTER_ENABLED' "$CONFIG_FILE"; then
    cat >> "$CONFIG_FILE" <<'EOF'
SUBCONVERTER_ENABLED = False
SUBCONVERTER_URL = "http://127.0.0.1:25500"
SUBCONVERTER_DEFAULT_TARGET = "v2ray"
SUBCONVERTER_EXTRA_SERVERS = []
EOF
    changed=1
  fi
  if [ "$changed" -eq 1 ]; then
    print_color yellow "Added missing config keys to config.py."
  fi
}

needs_config_setup() {
  local CONFIG_FILE="${INSTALL_DIR}/src/config.py"
  [ -f "$CONFIG_FILE" ] || return 0
  if grep -qE 'YOUR_BOT_TOKEN_HERE|your_panel_domain\.com' "$CONFIG_FILE"; then return 0; fi
  if grep -qE '^\s*ADMIN_ID\s*=\s*123456789\b' "$CONFIG_FILE"; then return 0; fi
  return 1
}

install_subconverter_docker() {
  local URL="$1"
  local PORT; PORT="$(echo "$URL" | sed -n 's/.*:KATEX_INLINE_OPEN[0-9]\{2,5\}KATEX_INLINE_CLOSE.*/\1/p')"
  [ -n "$PORT" ] || PORT="25500"

  print_color yellow "Preparing Docker for Subconverter (port ${PORT})..."
  if ! command -v docker >/dev/null 2>&1; then
    apt-get update -y >/dev/null 2>&1 || true
    apt-get install -y docker.io >/dev/null 2>&1 || true
    systemctl enable docker >/dev/null 2>&1 || true
    systemctl start docker >/dev/null 2>&1 || true
  fi

  docker rm -f subconverter >/dev/null 2>&1 || true
  docker run -d --name subconverter --restart=always -p "${PORT}:${PORT}" tindy2013/subconverter:latest >/dev/null 2>&1 || {
    print_color red "Failed to start Subconverter Docker container."
    return 1
  }
  print_color green "Subconverter is running on ${URL}"
}

install_or_reinstall() {
  ensure_root
  ensure_deps
  ensure_install_dir_vars

  local PREV_EXISTS=0; [ -d "$INSTALL_DIR" ] && PREV_EXISTS=1
  local BACKUP_DIR=""; local REUSE_CONFIG="N"
  if [ "$PREV_EXISTS" -eq 1 ]; then
    print_color yellow "Previous installation found at ${INSTALL_DIR}."
    read -rp "Reuse previous config.py and database? [y/N]: " REUSE_CONFIG
    REUSE_CONFIG=${REUSE_CONFIG:-N}
    print_color yellow "Stopping existing service..."
    systemctl stop "${SERVICE_NAME}.service" || true

    if [[ "$REUSE_CONFIG" =~ ^[Yy]$ ]]; then
      BACKUP_DIR="/tmp/vpn-bot-backup-$(date +%s)"
      mkdir -p "$BACKUP_DIR"
      [ -f "${INSTALL_DIR}/src/config.py" ] && cp "${INSTALL_DIR}/src/config.py" "${BACKUP_DIR}/config.py"
      [ -f "${INSTALL_DIR}/src/vpn_bot.db" ] && cp "${INSTALL_DIR}/src/vpn_bot.db" "${BACKUP_DIR}/vpn_bot.db"
      print_color green "Temporary backup saved to ${BACKUP_DIR}."
    fi

    print_color yellow "Removing previous installation..."
    rm -rf "$INSTALL_DIR"
  fi

  print_color yellow "Cloning repository..."
  git clone "$GITHUB_REPO" "$INSTALL_DIR"
  cd "$INSTALL_DIR"

  print_color yellow "Creating Python venv and installing dependencies..."
  python3 -m venv venv
  activate_venv
  pip install --upgrade pip
  if [ ! -f "requirements.txt" ]; then print_color red "requirements.txt not found."; deactivate_venv; exit 1; fi
  pip install -r requirements.txt || { print_color red "Failed to install Python packages."; deactivate_venv; exit 1; }
  deactivate_venv

  if [ -f "${INSTALL_DIR}/src/bot/keboards.py" ]; then
    mv "${INSTALL_DIR}/src/bot/keboards.py" "${INSTALL_DIR}/src/bot/keyboards.py"
  fi

  mkdir -p "${INSTALL_DIR}/backups"

  if [[ "$REUSE_CONFIG" =~ ^[Yy]$ ]] && [ -n "$BACKUP_DIR" ]; then
    print_color yellow "Restoring previous config and database..."
    [ -f "${BACKUP_DIR}/config.py" ] && cp "${BACKUP_DIR}/config.py" "${INSTALL_DIR}/src/config.py"
    [ -f "${BACKUP_DIR}/vpn_bot.db" ] && cp "${BACKUP_DIR}/vpn_bot.db" "${INSTALL_DIR}/src/vpn_bot.db"
    append_missing_keys_if_any
  else
    print_color blue "--- Bot Configuration ---"; configure_config_py
  fi

  if needs_config_setup; then
    print_color yellow "config.py contains default values. Starting configuration..."
    configure_config_py
  else
    read -rp "Review/edit config.py now? [y/N]: " EDIT_NOW; EDIT_NOW=${EDIT_NOW:-N}
    if [[ "$EDIT_NOW" =~ ^[Yy]$ ]]; then configure_config_py; fi
  fi

  local CONFIG_FILE="${INSTALL_DIR}/src/config.py"
  if grep -qE '^\s*SUBCONVERTER_ENABLED\s*=\s*True' "$CONFIG_FILE"; then
    local SUBC_URL; SUBC_URL="$(grep -E '^\s*SUBCONVERTER_URL\s*=' "$CONFIG_FILE" | sed -E 's/^[^"]*"([^"]+)".*/\1/')"
    if echo "$SUBC_URL" | grep -qiE '127\.0\.0\.1|localhost'; then
      read -rp "Deploy local Subconverter via Docker on ${SUBC_URL}? [y/N]: " DEPLOY_SUBC; DEPLOY_SUBC=${DEPLOY_SUBC:-N}
      if [[ "$DEPLOY_SUBC" =~ ^[Yy]$ ]]; then
        install_subconverter_docker "$SUBC_URL" || print_color red "Subconverter deployment failed."
      fi
    fi
  fi

  touch "${INSTALL_DIR}/src/bot.log"
  create_system_user
  chown -R vpn-bot:vpn-bot "${INSTALL_DIR}" || true
  chmod 640 "${INSTALL_DIR}/src/config.py" || true

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
  if [ -z "${INSTALL_DIR:-}" ] || [ ! -d "$INSTALL_DIR" ]; then print_color red "Installation not found."; exit 1; fi
  if [ ! -d "${INSTALL_DIR}/.git" ]; then print_color red "Not a git repository."; exit 1; fi

  print_color yellow "Stopping service for update..."
  systemctl stop "${SERVICE_NAME}" || true
  print_color yellow "Pulling latest changes..."
  git -C "$INSTALL_DIR" pull --ff-only
  print_color yellow "Updating Python deps..."
  activate_venv
  pip install --upgrade pip
  [ -f "${INSTALL_DIR}/requirements.txt" ] && pip install -r "${INSTALL_DIR}/requirements.txt"
  deactivate_venv

  if [ -f "${INSTALL_DIR}/src/bot/keboards.py" ]; then
    mv "${INSTALL_DIR}/src/bot/keboards.py" "${INSTALL_DIR}/src/bot/keyboards.py"
  fi

  touch "${INSTALL_DIR}/src/bot.log"
  chown vpn-bot:vpn-bot "${INSTALL_DIR}/src/bot.log" || true
  chmod 640 "${INSTALL_DIR}/src/config.py" || true
  print_color yellow "Restarting service..."
  systemctl start "${SERVICE_NAME}"
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
  if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then print_color yellow "Uninstall cancelled."; return; fi

  print_color yellow "Stopping and disabling service..."
  systemctl stop "${SERVICE_NAME}" || true
  systemctl disable "${SERVICE_NAME}" || true
  if [ -f "$SERVICE_FILE" ]; then print_color yellow "Removing service file..."; rm -f "$SERVICE_FILE"; systemctl daemon-reload; fi
  local DIR="${INSTALL_DIR:-/opt/vpn-bot}"
  if [ -d "$DIR" ]; then print_color yellow "Removing install directory: ${DIR}"; rm -rf "$DIR"; fi
  if [ -f "$CONF_FILE" ]; then print_color yellow "Removing saved settings: ${CONF_FILE}"; rm -f "$CONF_FILE"; fi
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
  load_conf
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