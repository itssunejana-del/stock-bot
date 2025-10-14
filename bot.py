from flask import Flask, request
import requests
import os
import time
import logging
import json
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
WEBHOOK_URL = "https://stock-bot-cj4s.onrender.com/webhook"
GARDEN_BOT_USERNAME = "@gargenstockbot"  # Исправленный username

# Переменная для отслеживания последнего ответа
last_bot_response = ""

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
        logger.info("✅ Уведомление отправлено")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

def send_to_garden_bot(message):
    """Отправляет сообщение боту @gargenstockbot"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": GARDEN_BOT_USERNAME,
        "text": message
    }
    try:
        response = requests.post(url, data=data)
        logger.info(f"📤 Отправлено боту: {message}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки боту: {e}")
        return False

def setup_webhook():
    """Настраивает вебхук для получения сообщений"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    data = {"url": WEBHOOK_URL}
    try:
        response = requests.post(url, data=data)
        logger.info(f"✅ Вебхук настроен: {response.json()}")
    except Exception as e:
        logger.error(f"❌ Ошибка настройки вебхука: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    """Получает сообщения от Telegram"""
    global last_bot_response
    
    try:
        data = request.json
        logger.info(f"📨 Получено сообщение от Telegram")
        
        # Сохраняем последний ответ для анализа
        if (data.get('message') and data['message'].get('text')):
            message_text = data['message']['text']
            last_bot_response = message_text
            
            # Ищем Помидор в сообщении
            if 'Помидор' in message_text:
                logger.info("🍅 НАЙДЕН ПОМИДОР В СООБЩЕНИИ!")
                send_telegram("🍅 🍅 🍅 ПОМИДОР ОБНАРУЖЕН! 🍅 🍅 🍅")
                send_telegram(f"📋 Сообщение: {message_text}")
        
        return 'OK'
    except Exception as e:
        logger.error(f"❌ Ошибка вебхука: {e}")
        return 'ERROR'

def auto_request_stock():
    """Автоматически запрашивает сток каждую минуту"""
    logger.info("🤖 Запускаю автоматические запросы стока...")
    
    while True:
        try:
            # Сначала отправляем /start боту
            logger.info("🔄 Отправляю /start боту...")
            success_start = send_to_garden_bot("/start")
            time.sleep(3)  # Ждем ответа бота
            
            # Затем запрашиваем сток
            logger.info("🔄 Отправляю '🌱 Сток'...")
            success_stock = send_to_garden_bot("🌱 Сток")
            
            if success_start and success_stock:
                logger.info("✅ Обе команды отправлены успешно")
            else:
                logger.error("❌ Ошибка отправки команд")
                
        except Exception as e:
            logger.error(f"❌ Ошибка автоматического запроса: {e}")
            
        time.sleep(60)  # Каждую минуту

@app.route('/')
def home():
    return "🤖 Автоматически запрашиваю сток у @gargenstockbot каждую минуту"

# Настраиваем вебхук при запуске
logger.info("🚀 Настраиваю вебхук...")
setup_webhook()

# Запускаем автоматические запросы
logger.info("🚀 Запускаю автоматические запросы...")
request_thread = threading.Thread(target=auto_request_stock)
request_thread.daemon = True
request_thread.start()

send_telegram("🔍 Система запущена! Автоматически запрашиваю сток у @gargenstockbot каждую минуту")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
