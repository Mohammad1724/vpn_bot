#!/bin/bash

# Stop on any error
set -e

# --- Configuration ---
PROJECT_NAME="your_bot_project" # <--- !!! REPLACE WITH YOUR PROJECT'S FOLDER NAME !!!
SERVICE_FILE="/etc/systemd/system/${PROJECT_NAME}.service"

echo "--- Starting Bot Uninstallation for '${PROJECT_NAME}' ---"

# 1. Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script as root (use sudo)"
  exit 1
fi

# 2. Stop and disable the service
echo "--- [1/2] Stopping and disabling the systemd service ---"
if systemctl is-active --quiet "${PROJECT_NAME}.service"; then
    systemctl stop "${PROJECT_NAME}.service"
    echo "Service stopped."
else
    echo "Service was not running."
fi

if systemctl is-enabled --quiet "${PROJECT_NAME}.service"; then
    systemctl disable "${PROJECT_NAME}.service"
    echo "Service disabled."
else
    echo "Service was not enabled."
fi

# 3. Remove the service file
echo "--- [2/2] Removing the service file ---"
if [ -f "$SERVICE_FILE" ]; then
    rm "$SERVICE_FILE"
    echo "Service file removed."
else
    echo "Service file not found."
fi

# 4. Reload systemd
systemctl daemon-reload

echo "--- Uninstallation Complete! ---"
echo "The systemd service has been removed."
echo "Project files at $(pwd) have NOT been deleted."
