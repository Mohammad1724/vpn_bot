#!/bin/bash
# Script to run VPN Bot

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Run bot with auto-restart
while true; do
    python3 vpn_bot.py
    echo "Bot crashed! Restarting in 5 seconds..."
    sleep 5
done
