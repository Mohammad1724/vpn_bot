#!/bin/bash
# Safe updater for vpn_bot

set -Eeuo pipefail

DEFAULT_SERVICE_NAME="vpn_bot"
CONF_FILE="/etc/vpn_bot.conf"

log() { echo -e "[update] $*"; }

ensure_root() {
  if [ "$(id -u)" -ne "0" ]; then
    echo "Please run this script as root (sudo)."
    exit 1
  fi
}

load_settings() {
  # Load from conf if available
  if [ -f "$CONF_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONF_FILE"
  fi
  SERVICE_NAME="${SERVICE_NAME:-$DEFAULT_SERVICE_NAME}"

  # Try to detect INSTALL_DIR from service file if missing
  if [ -z "${INSTALL_DIR:-}" ] && [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
    local wd
    wd="$(grep -E '^WorkingDirectory=' "/etc/systemd/system/${SERVICE_NAME}.service" | sed 's/^WorkingDirectory=//')"
    if [ -n "$wd" ]; then
      INSTALL_DIR="$(dirname "$wd")"
    fi
  fi

  # Fallback
  INSTALL_DIR="${INSTALL_DIR:-/opt/vpn-bot}"

  if [ ! -d "$INSTALL_DIR" ]; then
    echo "Install directory not found: $INSTALL_DIR"
    exit 1
  fi
}

update_repo() {
  if [ ! -d "${INSTALL_DIR}/.git" ]; then
    echo "Install directory is not a git repository: ${INSTALL_DIR}"
    exit 1
  fi
  log "Pulling latest changes from Git..."
  git -C "$INSTALL_DIR" pull --ff-only
}

ensure_venv_and_deps() {
  VENV_DIR="${INSTALL_DIR}/venv"
  PIP_BIN="${VENV_DIR}/bin/pip"
  PYTHON_BIN="${VENV_DIR}/bin/python"

  if [ ! -x "$PIP_BIN" ]; then
    log "Python venv not found. Creating one..."
    python3 -m venv "$VENV_DIR"
  fi

  log "Upgrading pip and installing/updating dependencies..."
  "$PIP_BIN" install --upgrade pip
  if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
    "$PIP_BIN" install -r "${INSTALL_DIR}/requirements.txt"
  else
    echo "requirements.txt not found at ${INSTALL_DIR}/requirements.txt"
    exit 1
  fi
}

restart_service() {
  log "Restarting systemd service: ${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}.service"
  log "Done. Check status with: systemctl status ${SERVICE_NAME}"
}

main() {
  ensure_root
  load_settings
  log "Detected install dir: ${INSTALL_DIR}"
  log "Service name: ${SERVICE_NAME}"

  update_repo
  ensure_venv_and_deps
  restart_service
}

main "$@"