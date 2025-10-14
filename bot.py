import requests
import time
import os

print("🎃 Бот запускается...")

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(message):
    print(f"Отправляю в Telegram: {message}")
    # Пока только тестируем, отправку настроим позже

send_telegram("🤖 Бот запущен на Render и работает 24/7!")

print("✅ Бот работает непрерывно!")

# Бесконечный цикл чтобы бот не останавливался
while True:
    time.sleep(60)  # Проверяем каждую минуту
    print("🔄 Бот все еще работает...")
