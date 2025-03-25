import logging
import asyncio
import threading
import os
import time
import google.generativeai as genai
import requests
import instaloader
from bs4 import BeautifulSoup
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, CallbackQueryHandler, filters
from aiogram import Bot, Dispatcher
import asyncio
import logging
import time
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from aiogram.utils import executor
import os
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی از فایل .env
load_dotenv()

# دریافت مقادیر از .env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")



# تنظیم لاگ‌گیری برای جلوگیری از نمایش پیام‌های تایم‌اوت
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.ERROR)
logger = logging.getLogger()

# تنظیم API Key برای Google Generative AI
genai.configure(api_key=GEMINI_API_KEY)

# تنظیم توکن ربات تلگرام و کانال

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot)
# بررسی عضویت کاربر در کانال
async def is_user_subscribed(user_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChatMember?chat_id={CHANNEL_USERNAME}&user_id={user_id}"
    try:
        response = requests.get(url, timeout=20).json()
        status = response.get("result", {}).get("status", "left")
        return status in ["member", "administrator", "creator"]
    except requests.exceptions.RequestException:
        return False

# دستور شروع ربات
async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("🎯 هوش مصنوعی", callback_data='ai_chat')],
        [InlineKeyboardButton("📥 دانلود ویدیو اینستاگرام", callback_data='download_instagram')],
        [InlineKeyboardButton("📥 دانلود ویدیو یوتیوب", callback_data='download_youtube')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('سلام! لطفاً یکی از گزینه‌های زیر را انتخاب کنید:', reply_markup=reply_markup)

# مدیریت کلیک روی دکمه‌ها
async def button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == 'ai_chat':
        context.user_data['mode'] = 'ai_chat'
        await query.message.reply_text("🤖 شما اکنون در حالت چت با هوش مصنوعی هستید. هر سوالی داری بپرس!")
    else:
        context.user_data['mode'] = query.data
        if not await is_user_subscribed(user_id):
            await query.message.reply_text(f"🚨 برای استفاده از این قابلیت، لطفا ابتدا در کانال ما عضو شوید: \n{CHANNEL_USERNAME}")
            return
        await query.message.reply_text("📥 لطفا لینک ویدیو را ارسال کنید:")

# دانلود و ارسال ویدیو یوتیوب
async def send_youtube_video(update: Update, url: str):
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'%(title)s.%(ext)s',
        'noplaylist': True
    }

    # اجرای تابع دانلود در یک ترد جداگانه
    await do_download(url, update.message.chat_id, update, ydl_opts)

    # اجرا در یک ترد جداگانه برای جلوگیری از بلاک شدن ربات
    thread = threading.Thread(target=do_download, args=(url, update.message.chat_id, update, ydl_opts), daemon=True)
    thread.start()

async def do_download(url, chat_id, update, ydl_opts):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # استخراج مدت زمان ویدئو (مدت زمان به ثانیه است)
            video_duration = info.get('duration', 0)
            
            # محاسبه مدت زمان تقریبی ارسال (می‌توانید با فرض سرعت ثابت ارسال، آن را تخمین بزنید)
            file_size = os.path.getsize(filename) / 1024  # اندازه فایل به کیلوبایت
            estimated_send_time = file_size / 10  # مدت زمان تقریبی ارسال (بر حسب ثانیه)

            # ارسال پیام به کاربر مبنی بر زمان تقریبی ارسال
            estimated_time_minutes = estimated_send_time / 60
            await update.message.reply_text(f"⏳ مدت زمان ویدئو: {video_duration // 60} دقیقه و {video_duration % 60} ثانیه\n"
                                           f"⏳ زمان تقریبی ارسال: {estimated_time_minutes:.2f} دقیقه")

        # ارسال ویدیو به کاربر
        await send_video(chat_id, filename, update)

    except Exception:
        pass  # هیچ پیامی به کاربر نمایش داده نمی‌شود

async def send_video(chat_id, filename, update):
    try:
        with open(filename, 'rb') as video_file:
            await update.message.reply_video(video_file)
    except Exception:
        pass  # هیچ پیامی به کاربر نمایش داده نمی‌شود
    finally:
        os.remove(filename)

# پردازش پیام‌های کاربر
async def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text
    mode = context.user_data.get('mode')

    if not await is_user_subscribed(user_id):
        await update.message.reply_text(f"🚨 شما عضو کانال نیستید! لطفا ابتدا عضو شوید: {CHANNEL_USERNAME}")
        return

    if mode == 'ai_chat':
        try:
            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            response = model.generate_content(text)
            await update.message.reply_text(response.text)
        except Exception:
            pass  
        return

    if mode == 'download_youtube' and 'youtube.com' in text:
        # ارسال پیام "در حال دانلود..." به کاربر
        await update.message.reply_text("🔄 در حال دانلود ویدیو از یوتیوب... لطفا منتظر بمانید.")
        await send_youtube_video(update, text)
    elif mode == 'download_instagram' and 'instagram.com' in text:
        # ارسال پیام "در حال دانلود..." به کاربر
        await update.message.reply_text("🔄 در حال دانلود ویدیو از اینستاگرام... لطفا منتظر بمانید.")
        await send_instagram_video(update, text)
    else:
        await update.message.reply_text("❌ لینک معتبر نیست!")

# دانلود و ارسال ویدیو اینستاگرام
async def send_instagram_video(update: Update, url: str):
    L = instaloader.Instaloader()
    try:
        post = instaloader.Post.from_shortcode(L.context, url.split('/')[-2])
        video_url = post.video_url
        await update.message.reply_video(video_url)
    except Exception:
        pass  # هیچ پیامی به کاربر نمایش داده نمی‌شود
# تابع اصلی برای اجرای ربات
def main():
    # نمایش پیام در ترمینال
    print("🔄 bot started..")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == '__main__':
    main()
