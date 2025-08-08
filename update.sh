#!/bin/bash

# Stop on any error
set -e

# --- Configuration ---
PROJECT_NAME="your_bot_project" # <--- !!! REPLACE WITH YOUR PROJECT'S FOLDER NAME !!!
PROJECT_DIR=$(pwd)
VENV_DIR="$PROJECT_DIR/venv"

echo "--- Starting Bot Update for '${PROJECT_NAME}' ---"

echo "--- [1/4] Pulling latest changes from Git ---"
git pull

echo "--- [2/4] Activating virtual environment ---"
source "$VENV_DIR/bin/activate"

echo "--- [3/4] Updating dependencies ---"
pip install --upgrade pip
pip install -r "$PROJECT_DIR/requirements.txt"

echo "--- [4/4] Deactivating virtual environment and restarting service ---"
deactivate
sudo systemctl restart "${PROJECT_NAME}.service"

echo "--- Update Complete! ---"
echo "Bot has been updated and restarted."
echo "Check status with: sudo systemctl status ${PROJECT_NAME}"
