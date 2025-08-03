# setup.py
import os
import sys

def colored_input(prompt):
    """یک تابع برای نمایش ورودی به رنگی دیگر برای خوانایی بهتر"""
    # کد ANSI برای رنگ سبز
    GREEN = '\033[92m'
    # کد ANSI برای ریست کردن رنگ
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

    # دیکشنری برای نگهداری سوالات و متغیرهای محیطی
    # (توضیحات به کاربر نشان داده می‌شود)
    config_vars = {
        'TOKEN': "توکن ربات تلگرام (از BotFather دریافت کنید): ",
        'ADMIN_ID': "آیدی عددی اکانت ادمین تلگرام (از @userinfobot دریافت کنید): ",
        'CARD_NUMBER': "شماره کارت برای واریز وجه: ",
        'CARD_HOLDER': "نام صاحب کارت: ",
        'HIDDIFY_PANEL_DOMAIN': "دامنه پنل Hiddify (بدون http یا https، مثلا: my.domain.com): ",
        'HIDDIFY_ADMIN_UUID': "کلید UUID ادمین پنل Hiddify: "
    }

    env_content = ""
    for var, prompt in config_vars.items():
        while True:
            value = colored_input(prompt)
            if value:
                # اطمینان از اینکه دامنه بدون پروتکل است
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
        print("اکنون می‌توانید ربات را با دستور زیر اجرا کنید:")
        print("python3 main.py")
    except IOError as e:
        print(f"\n❌ خطایی در نوشتن فایل .env رخ داد: {e}")
        sys.exit(1)

if __name__ == "__main__":
    create_env_file()
