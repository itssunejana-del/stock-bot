from flask import Flask
import requests
import os
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
        logger.info("✅ Уведомление отправлено")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

def safe_monitor():
    """Безопасный мониторинг"""
    logger.info("🎃 Безопасный мониторинг запущен")
    send_telegram("🤖 Бот работает! Ожидаю настройки...")
    
    counter = 0
    while True:
        counter += 1
        logger.info(f"🔍 Проверка #{counter} - система готова")
        time.sleep(60)

@app.route('/')
def home():
    return "🎃 Система мониторинга готова к настройке"

# Запускаем
import threading
logger.info("🚀 Запускаю базовый монитор...")
monitor_thread = threading.Thread(target=safe_monitor)
monitor_thread.daemon = True
monitor_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
