from flask import Flask
import requests
import os
import time
import logging
import threading
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

# Храним ВРЕМЯ последнего сообщения
last_message_time = None
processed_messages = set()

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено: {text}")
            return True
        else:
            return False
    except:
        return False

def get_full_message_text(message):
    """Извлекает ВЕСЬ текст из сообщения"""
    full_text = message.get('content', '')
    
    embeds = message.get('embeds', [])
    for embed in embeds:
        full_text += f" {embed.get('title', '')}"
        full_text += f" {embed.get('description', '')}"
        full_text += f" {embed.get('footer', {}).get('text', '')}"
        
        for field in embed.get('fields', []):
            full_text += f" {field.get('name', '')}"
            full_text += f" {field.get('value', '')}"
    
    return full_text

def get_message_time(message):
    """Получает время сообщения"""
    timestamp = message['timestamp'].replace('Z', '+00:00')
    return datetime.fromisoformat(timestamp)

def check_discord_messages():
    global last_message_time
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=5"  # Только 5 последних
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            logger.info(f"🔍 Проверяю {len(messages)} сообщений")
            
            for message in messages:
                message_id = message['id']
                author = message.get('author', {}).get('username', 'Unknown')
                
                # Только сообщения Вулкана
                if 'Vulcan' not in author:
                    continue
                
                message_time = get_message_time(message)
                full_text = get_full_message_text(message)
                
                logger.info(f"📄 Сообщение: {full_text[:80]}...")
                
                # 🔴 ВАЖНО: Проверяем только СВЕЖИЕ сообщения
                if last_message_time and message_time <= last_message_time:
                    continue  # Пропускаем старые сообщения
                
                # Обновляем время последнего сообщения
                last_message_time = message_time
                
                # 🔴 ИЩЕМ ТОМАТ ТОЛЬКО В НОВЫХ СООБЩЕНИЯХ
                if 'Tomato' in full_text or 'To...' in full_text:
                    logger.info("🎯 ОБНАРУЖЕН ТОМАТ! Отправляю в Telegram...")
                    send_telegram("🍅 Томат в стоке!")
                    return True
            
            return False
        else:
            return False
            
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        return False

def monitoring_loop():
    logger.info("🔄 Мониторинг запущен (ищем томаты в НОВЫХ сообщениях)")
    
    while True:
        try:
            check_discord_messages()
            time.sleep(10)
        except:
            time.sleep(30)

@app.route('/')
def home():
    return """
    <h1>🍅 Умный мониторинг томатов</h1>
    <p>Бот проверяет только НОВЫЕ сообщения Вулкана</p>
    <p>Не спамит уведомлениями о старых стоках</p>
    <p><a href="/test_telegram">Тест Telegram</a></p>
    """

@app.route('/test_telegram')
def test_telegram():
    success = send_telegram("✅ Умный бот работает! Жду новые томаты.")
    return f"Тест: {'✅ Отправлено' if success else '❌ Ошибка'}"

@app.route('/reset')
def reset():
    global last_message_time
    last_message_time = None
    return "✅ Сброшено! Буду считать следующее сообщение новым."

# Запускаем мониторинг
threading.Thread(target=monitoring_loop, daemon=True).start()

if __name__ == '__main__':
    logger.info("🚀 УМНЫЙ БОТ ЗАПУЩЕН - жду новые сообщения с томатами!")
    app.run(host='0.0.0.0', port=5000)
