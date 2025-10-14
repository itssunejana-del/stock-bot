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

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        response = requests.post(url, data=data)
        logger.info("✅ Сообщение отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")

def safe_monitor():
    """Безопасный монитор без Discord"""
    logger.info("🛡️ Безопасный режим: Discord отключен")
    send_telegram("🛡️ Бот в безопасном режиме. Ожидаю снятия ограничения Discord.")
    
    counter = 0
    while True:
        counter += 1
        logger.info(f"🔒 Безопасный режим... (цикл #{counter})")
        time.sleep(300)  # Проверяем каждые 5 минут

@app.route('/')
def home():
    return "🎃 Бот в безопасном режиме. Ожидаю снятия ограничения Discord."

# Запускаем безопасный монитор
logger.info("🛡️ Запускаю безопасный режим...")
monitor_thread = threading.Thread(target=safe_monitor)
monitor_thread.daemon = True
monitor_thread.start()

if __name__ == '__main__':
    logger.info("🚀 Запускаю веб-сервер...")
    app.run(host='0.0.0.0', port=5000)
