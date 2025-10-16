from flask import Flask, request
import requests
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')  # Безопасно!

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
        logger.info("✅ Уведомление отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

def send_discord_test():
    """Отправляет тестовое сообщение в Discord через вебхук"""
    data = {
        "content": "🍅 Тестовое сообщение: Tomato x5"
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data)
        if response.status_code == 204:
            logger.info("✅ Тестовое сообщение отправлено в Discord")
            send_telegram("✅ Вебхук работает! Сообщение отправлено в Discord")
        else:
            logger.error(f"❌ Ошибка Discord: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Discord: {e}")

@app.route('/test')
def test_webhook():
    """Тестирует вебхук"""
    send_discord_test()
    return "Тестовое сообщение отправлено в Discord"

@app.route('/')
def home():
    return "🤖 Бот работает! Используйте /test для проверки вебхука"

logger.info("🚀 Сервер запущен")
send_telegram("🔍 Бот запущен! Готов к работе!")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
