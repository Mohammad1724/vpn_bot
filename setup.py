# setup.py
import os
import sys

def colored_input(prompt):
    """یک تابع برای نمایش ورودی به رنگی دیگر برای خوانایی بهتر"""
    GREEN = '\033[92m'
    RESET = '\033[0m'
    return input(f"{GREEN}{prompt}{RESET}")

def create_env_file():
    """
    این تابع فایل .env را با پرسیدن سوالات از کاربر ایجاد می‌کند.
    """
    env_file_path = '.env'

    if os.path.exists(env_file_path):
        print("فایل .env از قبل وجود دارد.")
        overwrite = colored_input("آیا می‌خواهید آن را بازنویسی کنید؟ (y/n): ").lower()
        if overwrite != 'y':
            print("عملیات لغو شد.")
            sys.exit()

    print("--- شروع راه‌اندازی ربات فروش Hiddify ---")
    print("لطفاً اطلاعات زیر را با دقت وارد کنید.\n")

    config_vars = {
        'TOKEN': "توکن ربات تلگرام (از BotFather دریافت کنید): ",
        'ADMIN_ID': "آیدی عددی اکانت ادمین تلگرام (از @userinfobot دریافت کنید): ",
        'CARD_NUMBER': "شماره کارت برای واریز وجه: ",
        'CARD_HOLDER': "نام صاحب کارت: ",
        'HIDDIFY_PANEL_DOMAIN': "دامنه پنل Hiddify (بدون http یا https، مثلا: my.domain.com): ",
        'HIDDIFY_ADMIN_UUID': "کلید UUID ادمین پنل Hiddify (از تنظیمات پنل کپی کنید): ",
        'HIDDIFY_ADMIN_USER': "نام کاربری ادمین پنل Hiddify (معمولا admin است): ",
        'HIDDIFY_ADMIN_PASS': "رمز عبور ادمین پنل Hiddify: "
    }

    env_content = ""
    for var, prompt in config_vars.items():
        while True:
            value = colored_input(prompt)
            if value:
                if var == 'HIDDIFY_PANEL_DOMAIN':
                    value = value.replace('https://', '').replace('http://', '').strip('/')
                
                env_content += f'{var}="{value}"\n'
                break
            else:
                print("این فیلد نمی‌تواند خالی باشد. لطفاً مقداری وارد کنید.")
    
    try:
        with open(env_file_path, 'w', encoding='utf-8') as f:
            f.write(env_content)
        print("\n✅ فایل .env با موفقیت ایجاد شد!")
        print("اکنون پیش‌نیازها را با دستور 'pip install -r requirements.txt' نصب کنید.")
        print("سپس ربات را با دستور 'python3 main.py' اجرا نمایید.")
    except IOError as e:
        print(f"\n❌ خطایی در نوشتن فایل .env رخ داد: {e}")
        sys.exit(1)

if __name__ == "__main__":
    create_env_file()