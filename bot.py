from flask import Flask
import requests
import os
import threading
import time
import logging

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(message):
    logger.info(f"Отправляю в Telegram: {message}")
    # Пока только логируем

def bot_worker():
    logger.info("🎃 Бот-воркер запущен!")
    send_telegram("🤖 Бот запущен на Render и работает 24/7!")
    
    counter = 0
    while True:
        counter += 1
        logger.info(f"🔄 Бот проверяет сообщения... (проверка #{counter})")
        time.sleep(30)  # Проверяем каждые 30 секунд для теста

@app.route('/')
def home():
    return "🎃 Pumpkin Bot работает! Проверяю Discord..."

# Запускаем бота сразу при импорте
logger.info("✅ Запускаю бота...")
bot_thread = threading.Thread(target=bot_worker)
bot_thread.daemon = True
bot_thread.start()

if __name__ == '__main__':
    logger.info("🚀 Запускаю веб-сервер...")
    app.run(host='0.0.0.0', port=5000)
