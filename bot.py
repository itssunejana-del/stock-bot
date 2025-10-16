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
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
        logger.info("✅ Уведомление отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

def check_discord_connection():
    """Проверяет подключение к Discord API"""
    try:
        logger.info("🔄 Проверяю подключение к Discord...")
        logger.info(f"📝 Токен: {DISCORD_TOKEN[:10]}...")  # Только первые 10 символов
        logger.info(f"📝 ID канала: {DISCORD_CHANNEL_ID}")
        
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers)
        logger.info(f"📡 Статус ответа Discord: {response.status_code}")
        
        if response.status_code == 200:
            messages = response.json()
            logger.info(f"📨 Получено сообщений: {len(messages)}")
            return True, messages[0]['content'] if messages else "Канал пуст"
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code} - {response.text}")
            return False, None
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка подключения: {e}")
        return False, None

def discord_monitor():
    """Мониторит канал Discord"""
    logger.info("🚀 ЗАПУСКАЮ DSCORD МОНИТОР...")
    
    # Тестовое подключение
    success, message = check_discord_connection()
    
    if success:
        send_telegram("✅ Discord подключение успешно! Мониторю Tomato...")
        logger.info("🔍 Начинаю мониторинг Tomato...")
    else:
        send_telegram("❌ Ошибка подключения к Discord")
        logger.error("❌ НЕ УДАЛОСЬ ПОДКЛЮЧИТЬСЯ К DISCORD")
        return
    
    last_detected = False
    
    while True:
        try:
            found, message = check_discord_connection()
            
            if found and 'Tomato' in str(message) and not last_detected:
                logger.info("🍅 TOMATO ОБНАРУЖЕН!")
                send_telegram("🍅 TOMATO В ПРОДАЖЕ! 🍅")
                send_telegram(f"📋 {message}")
                last_detected = True
            elif not found:
                last_detected = False
                
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            
        time.sleep(30)

@app.route('/')
def home():
    return "🍅 Мониторю канал на предмет Tomato"

# Запускаем монитор
logger.info("🚀 Запускаю систему...")
send_telegram("🔍 Бот запущен! Проверяю подключение...")
monitor_thread = threading.Thread(target=discord_monitor)
monitor_thread.daemon = True
monitor_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
