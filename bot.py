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
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')  # Добавим токен Discord

# ID канала #стоки-гроу (нужно получить)
DISCORD_CHANNEL_ID = "ВАШ_ID_КАНАЛА_СТОКИ_ГРОУ"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
        logger.info("✅ Уведомление отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

def check_discord_channel():
    """Проверяет сообщения в канале Discord"""
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            messages = response.json()
            # Берем последнее сообщение
            if messages and 'Tomato' in messages[0]['content']:
                return True, messages[0]['content']
        return False, None
    except Exception as e:
        logger.error(f"❌ Ошибка проверки Discord: {e}")
        return False, None

def discord_monitor():
    """Мониторит канал Discord"""
    logger.info("🔍 Начинаю мониторинг канала #стоки-гроу...")
    send_telegram("🔍 Начинаю мониторинг стока! Ожидаю Tomato...")
    
    last_detected = False
    
    while True:
        try:
            found, message = check_discord_channel()
            
            if found and not last_detected:
                logger.info("🍅 TOMATO ОБНАРУЖЕН!")
                send_telegram("🍅 TOMATO В ПРОДАЖЕ! 🍅")
                send_telegram(f"📋 Актуальный сток:\n{message}")
                last_detected = True
            elif not found:
                last_detected = False
                
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            
        time.sleep(60)  # Проверяем каждую минуту

@app.route('/')
def home():
    return "🍅 Мониторю канал #стоки-гроу на предмет Tomato"

# Запускаем монитор
logger.info("🚀 Запускаю Discord монитор...")
monitor_thread = threading.Thread(target=discord_monitor)
monitor_thread.daemon = True
monitor_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
