from flask import Flask
import requests
import os
import time
import logging
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GARDEN_BOT_ID = 7859360521  # ID бота @gargenstockbot

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
        logger.info("✅ Уведомление отправлено")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

def send_to_garden_bot(message):
    """Отправляет сообщение боту @gargenstockbot по ID"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": GARDEN_BOT_ID, "text": message}
    try:
        response = requests.post(url, data=data)
        if response.json().get('ok'):
            logger.info(f"📤 Отправлено боту: {message}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки: {response.json()}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки боту: {e}")
        return False

def monitor_responses():
    """Мониторит ответы от @gargenstockbot"""
    logger.info("👂 Начинаю мониторинг ответов...")
    last_update_id = 0
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": 30}
            response = requests.get(url, params=params).json()
            
            for update in response.get('result', []):
                last_update_id = update['update_id']
                
                if (update.get('message') and 
                    update['message'].get('text') and
                    'Помидор' in update['message']['text']):
                    
                    logger.info("🍅 НАЙДЕН ПОМИДОР В ОТВЕТЕ!")
                    send_telegram("🍅 🍅 🍅 ПОМИДОР ОБНАРУЖЕН! 🍅 🍅 🍅")
                    send_telegram(f"📋 Сообщение: {update['message']['text']}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            
        time.sleep(5)

def auto_request_stock():
    """Автоматически запрашивает сток"""
    logger.info("🤖 Запускаю автоматические запросы...")
    
    while True:
        try:
            # Сначала отправляем /start
            logger.info("🔄 Отправляю /start боту...")
            success_start = send_to_garden_bot("/start")
            time.sleep(3)
            
            # Затем запрашиваем сток
            logger.info("🔄 Отправляю '🌱 Сток'...")
            success_stock = send_to_garden_bot("🌱 Сток")
            
            if success_start and success_stock:
                logger.info("✅ Команды отправлены")
            else:
                logger.error("❌ Ошибка отправки команд")
                
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            
        time.sleep(60)

@app.route('/')
def home():
    return "🤖 Мониторю @gargenstockbot через getUpdates"

# Запускаем оба потока
logger.info("🚀 Запускаю систему...")
monitor_thread = threading.Thread(target=monitor_responses)
monitor_thread.daemon = True
monitor_thread.start()

request_thread = threading.Thread(target=auto_request_stock)
request_thread.daemon = True
request_thread.start()

send_telegram("🔍 Система запущена! Мониторю @gargenstockbot по ID")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
