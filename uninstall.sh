#!/bin/bash
# Robust uninstaller for vpn_bot

set -Eeuo pipefail

SERVICE_NAME="vpn_bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CONF_FILE="/etc/vpn_bot.conf"
DEFAULT_INSTALL_DIR="/opt/vpn-bot"

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

ensure_root() {
  if [ "$(id -u)" -ne "0" ]; then
    print_color red "Please run this script as root (sudo)."
    exit 1
  fi
}

ask_yes_no() {
  local PROMPT="$1"
  read -rp "${PROMPT} [y/N]: " REPLY
  [[ "$REPLY" =~ ^[Yy]$ ]]
}

load_conf() {
  if [ -f "$CONF_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONF_FILE"
  fi
  # Try to detect from service file if not set
  if [ -z "${INSTALL_DIR:-}" ] && [ -f "$SERVICE_FILE" ]; then
    local WD
    WD="$(grep -E '^WorkingDirectory=' "$SERVICE_FILE" | sed 's/^WorkingDirectory=//')"
    INSTALL_DIR="${WD%/src}"
  fi
  # Fallback to default
  INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
}

stop_disable_service() {
  print_color yellow "Stopping and disabling systemd service..."
  if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    systemctl stop "${SERVICE_NAME}.service"
    print_color green "Service stopped."
  else
    print_color yellow "Service not running."
  fi

  if systemctl is-enabled --quiet "${SERVICE_NAME}.service"; then
    systemctl disable "${SERVICE_NAME}.service"
    print_color green "Service disabled."
  else
    print_color yellow "Service was not enabled."
  fi
}

remove_service_file() {
  print_color yellow "Removing service file..."
  if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    print_color green "Service file removed: $SERVICE_FILE"
  else
    print_color yellow "Service file not found: $SERVICE_FILE"
  fi
  systemctl daemon-reload
  systemctl reset-failed || true
}

remove_install_dir() {
  if [ -d "$INSTALL_DIR" ]; then
    if ask_yes_no "Remove install directory '${INSTALL_DIR}'?"; then
      rm -rf "$INSTALL_DIR"
      print_color green "Removed: ${INSTALL_DIR}"
    else
      print_color yellow "Skipped removing install directory."
    fi
  else
    print_color yellow "Install directory not found: ${INSTALL_DIR}"
  fi
}

remove_conf_file() {
  if [ -f "$CONF_FILE" ]; then
    if ask_yes_no "Remove saved settings file '${CONF_FILE}'?"; then
      rm -f "$CONF_FILE"
      print_color green "Removed: ${CONF_FILE}"
    else
      print_color yellow "Skipped removing settings file."
    fi
  fi
}

remove_system_user() {
  if id -u vpn-bot >/dev/null 2>&1; then
    if ask_yes_no "Remove system user 'vpn-bot'?"; then
      # Try to remove user; home may already be deleted
      userdel vpn-bot || true
      print_color green "User 'vpn-bot' removed (if existed)."
    else
      print_color yellow "Skipped removing user 'vpn-bot'."
    fi
  fi
}

main() {
  print_color blue "--- Uninstalling '${SERVICE_NAME}' ---"
  ensure_root
  load_conf

  print_color yellow "Detected install directory: ${INSTALL_DIR}"

  stop_disable_service
  remove_service_file
  remove_install_dir
  remove_conf_file
  remove_system_user

  print_color blue "--- Uninstallation complete ---"
  print_color yellow "If you kept the install directory, project files are still present at: ${INSTALL_DIR}"
}

main "$@"