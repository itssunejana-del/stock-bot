from flask import Flask, request
import requests
import os
import time
import logging
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
WEBHOOK_URL = "https://stock-bot-cj4s.onrender.com/webhook"  # Ваш URL

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
        logger.info("✅ Уведомление отправлено")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

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
    try:
        data = request.json
        logger.info(f"📨 Получено сообщение от Telegram")
        
        # Проверяем что это сообщение от @gardenstockbot
        if (data.get('message') and 
            data['message'].get('text') and 
            'Помидор' in data['message']['text']):
            
            logger.info("🍅 НАЙДЕН ПОМИДОР В СООБЩЕНИИ!")
            send_telegram("🍅 🍅 🍅 ПОМИДОР ОБНАРУЖЕН! 🍅 🍅 🍅")
            send_telegram(f"📋 Сообщение: {data['message']['text']}")
        
        return 'OK'
    except Exception as e:
        logger.error(f"❌ Ошибка вебхука: {e}")
        return 'ERROR'

@app.route('/')
def home():
    return "🤖 Мониторю сообщения от @gardenstockbot"

# Настраиваем вебхук при запуске
logger.info("🚀 Настраиваю вебхук...")
setup_webhook()
send_telegram("🔍 Вебхук настроен! Ожидаю сообщения от @gardenstockbot")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
