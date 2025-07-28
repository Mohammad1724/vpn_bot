#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

show_menu() {
    echo -e "${BLUE}🤖 مدیریت ربات فروش VPN${NC}"
    echo "=========================="
    echo "1. شروع ربات"
    echo "2. توقف ربات" 
    echo "3. وضعیت ربات"
    echo "4. مشاهده لاگ‌ها"
    echo "5. ویرایش تنظیمات"
    echo "6. بازنشانی ربات"
    echo "7. تنظیم فایروال"
    echo "8. خروج"
    echo -n "انتخاب کنید [1-8]: "
}

start_bot() {
    echo -e "${YELLOW}🚀 در حال شروع ربات...${NC}"
    systemctl enable vpn-bot
    systemctl start vpn-bot
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ ربات با موفقیت شروع شد${NC}"
    else
        echo -e "${RED}❌ خطا در شروع ربات${NC}"
    fi
}

stop_bot() {
    echo -e "${YELLOW}🛑 در حال توقف ربات...${NC}"
    systemctl stop vpn-bot
    echo -e "${GREEN}✅ ربات متوقف شد${NC}"
}

status_bot() {
    echo -e "${BLUE}📊 وضعیت ربات:${NC}"
    systemctl status vpn-bot --no-pager -l
}

show_logs() {
    echo -e "${BLUE}📋 لاگ‌های ربات:${NC}"
    echo "برای خروج Ctrl+C بزنید"
    journalctl -u vpn-bot -f
}

edit_config() {
    echo -e "${YELLOW}⚙️ ویرایش تنظیمات...${NC}"
    nano config.py
    echo -e "${GREEN}✅ تنظیمات ذخیره شد${NC}"
    echo -e "${YELLOW}🔄 برای اعمال تغییرات ربات را restart کنید${NC}"
}

restart_bot() {
    echo -e "${YELLOW}🔄 در حال بازنشانی ربات...${NC}"
    systemctl restart vpn-bot
    echo -e "${GREEN}✅ ربات بازنشانی شد${NC}"
}

setup_firewall() {
    echo -e "${YELLOW}🔥 تنظیم فایروال...${NC}"
    ufw --force enable
    ufw allow ssh
    ufw allow 443
    ufw allow 80
    echo -e "${GREEN}✅ فایروال پیکربندی شد${NC}"
}

while true; do
    show_menu
    read choice
    case $choice in
        1) start_bot ;;
        2) stop_bot ;;
        3) status_bot ;;
        4) show_logs ;;
        5) edit_config ;;
        6) restart_bot ;;
        7) setup_firewall ;;
        8) echo -e "${GREEN}👋 خداحافظ!${NC}"; exit 0 ;;
        *) echo -e "${RED}❌ انتخاب نامعتبر${NC}" ;;
    esac
    echo
    read -p "برای ادامه Enter بزنی
    د..."
done
