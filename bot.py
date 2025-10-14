import requests
import time
import os

print("🎃 Бот запускается...")

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(message):
    print(f"Отправляю в Telegram: {message}")

send_telegram("🤖 Бот запущен на Render!")

print("✅ Бот работает!")
time.sleep(10)
