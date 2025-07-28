import os
import json
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی
load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # ID تلگرام شما

# مسیر فایل JSON برای ذخیره کانفیگ‌ها
CONFIG_FILE = "configs.json"

# ایجاد نمونه کلاینت بات
app = Client("vpn_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# بارگذاری یا ایجاد فایل کانفیگ‌ها
def load_configs():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return []

def save_configs(configs):
    with open(CONFIG_FILE, "w") as f:
        json.dump(configs, f, indent=4)

# دستور /start
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply(
        "سلام! به ربات فروش VPN خوش آمدید.\n"
        "دستورات:\n"
        "/listconfigs - نمایش لیست کانفیگ‌ها\n"
        "/getconfig [id] - دریافت کانفیگ با شماره مشخص\n"
        "برای اطلاعات بیشتر با ادمین تماس بگیرید."
    )

# دستور /addconfig (فقط برای ادمین)
@app.on_message(filters.command("addconfig") & filters.user(ADMIN_ID))
async def add_config(client, message):
    if len(message.command) < 2:
        await message.reply("لطفاً کانفیگ را وارد کنید. مثال:\n/addconfig vless://...")
        return
    config = message.text.split(" ", 1)[1]  # دریافت کانفیگ از پیام
    configs = load_configs()
    config_id = len(configs) + 1
    configs.append({"id": config_id, "config": config})
    save_configs(configs)
    await message.reply(f"کانفیگ با شماره {config_id} اضافه شد.")

# دستور /listconfigs
@app.on_message(filters.command("listconfigs"))
async def list_configs(client, message):
    configs = load_configs()
    if not configs:
        await message.reply("هیچ کانفیگی موجود نیست.")
        return
    buttons = [
        [InlineKeyboardButton(f"کانفیگ شماره {c['id']}", callback_data=f"get_{c['id']}")]
        for c in configs
    ]
    await message.reply(
        "لیست کانفیگ‌های موجود:", reply_markup=InlineKeyboardMarkup(buttons)
    )

# دستور /getconfig
@app.on_message(filters.command("getconfig"))
async def get_config(client, message):
    if len(message.command) < 2:
        await message.reply("لطفاً شماره کانفیگ را وارد کنید. مثال:\n/getconfig 1")
        return
    try:
        config_id = int(message.command[1])
        configs = load_configs()
        for config in configs:
            if config["id"] == config_id:
                await message.reply(f"کانفیگ شماره {config_id}:\n{config['config']}")
                return
        await message.reply("کانفیگ یافت نشد.")
    except ValueError:
        await message.reply("شماره کانفیگ باید عدد باشد.")

# مدیریت دکمه‌های اینلاین
@app.on_callback_query()
async def handle_callback(client, callback_query):
    config_id = int(callback_query.data.split("_")[1])
    configs = load_configs()
    for config in configs:
        if config["id"] == config_id:
            await callback_query.message.reply(f"کانفیگ شماره {config_id}:\n{config['config']}")
            await callback_query.answer("کانفیگ ارسال شد.")
            return
    await callback_query.answer("کانفیگ یافت نشد.")

# اجرای بات
if __name__ == "__main__":
    app.run()
