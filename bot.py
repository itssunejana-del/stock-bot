from flask import Flask, request
import requests
import os
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
        logger.info("✅ Уведомление отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

@app.route('/webhook', methods=['POST'])
def discord_webhook():
    """Получает сообщения от Discord вебхука"""
    try:
        data = request.json
        
        # Проверяем что это сообщение о стоке
        if data.get('content') and 'Tomato' in data['content']:
            logger.info("🍅 TOMATO ОБНАРУЖЕН ЧЕРЕЗ ВЕБХУК!")
            send_telegram("🍅 TOMATO В ПРОДАЖЕ! 🍅")
            send_telegram(f"📋 {data['content']}")
        
        return 'OK'
    except Exception as e:
        logger.error(f"❌ Ошибка вебхука: {e}")
        return 'ERROR'

@app.route('/')
def home():
    return "🎯 Готов принимать вебхуки от Discord"

logger.info("🚀 Сервер вебхука запущен")
send_telegram("🔍 Система готова к приему вебхуков!")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
