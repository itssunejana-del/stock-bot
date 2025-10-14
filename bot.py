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

def simulate_bot_check():
    """Имитирует проверку бота @gardenstockbot"""
    logger.info("🤖 Проверяю @gardenstockbot...")
    
    # В реальности здесь будет код для чтения сообщений от бота
    # Пока просто тестируем систему
    
    # Если бы мы могли читать сообщения, мы бы:
    # 1. Отправляли боту "🌱 Сток"
    # 2. Читали ответ
    # 3. Искали "Помидор" в ответе
    
    return False  # Пока всегда возвращаем False для теста

def bot_monitor():
    """Мониторинг Telegram бота"""
    logger.info("🤖 Запускаю мониторинг @gardenstockbot...")
    send_telegram("🔍 ТЕСТ: Начинаю мониторинг @gardenstockbot на Помидор!")
    
    while True:
        try:
            found = simulate_bot_check()
            
            if found:
                logger.info("🍅 ПОМИДОР НАЙДЕН В СТОКЕ!")
                send_telegram("🍅 🍅 🍅 ПОМИДОР В ПРОДАЖЕ! 🍅 🍅 🍅")
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            
        time.sleep(60)  # 1 минута

@app.route('/')
def home():
    return "🍅 ТЕСТ: Мониторю @gardenstockbot на предмет Помидора"

# Запускаем
import threading
logger.info("🚀 Запускаю монитор бота...")
monitor_thread = threading.Thread(target=bot_monitor)
monitor_thread.daemon = True
monitor_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
