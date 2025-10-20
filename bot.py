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

# Храним ID последнего проверенного сообщения
last_checked_id = None

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

def check_discord_messages():
    global last_checked_id
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=5"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            
            # Сортируем от нового к старому
            messages.sort(key=lambda x: x['id'], reverse=True)
            
            found_tomato = False
            
            for message in messages:
                message_id = message['id']
                author = message.get('author', {}).get('username', 'Unknown')
                
                # Только сообщения Вулкана
                if 'Vulcan' not in author:
                    continue
                
                # Если дошли до последнего проверенного сообщения - останавливаемся
                if last_checked_id and message_id <= last_checked_id:
                    break
                
                full_text = get_full_message_text(message)
                logger.info(f"🔍 Проверяю новое сообщение: {full_text[:80]}...")
                
                # Ищем ТОМАТ в новом сообщении
                if 'Tomato' in full_text or 'To...' in full_text:
                    logger.info("🎯 ОБНАРУЖЕН ТОМАТ В НОВОМ СООБЩЕНИИ!")
                    send_telegram("🍅 Томат в стоке!")
                    found_tomato = True
                    break  # Нашли томат - выходим
            
            # Обновляем ID последнего проверенного сообщения
            if messages:
                last_checked_id = messages[0]['id']  # ID самого нового сообщения
            
            return found_tomato
        else:
            return False
            
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        return False

def monitoring_loop():
    logger.info("🔄 УМНЫЙ мониторинг запущен (только новые сообщения)")
    
    # При старте запоминаем текущие сообщения как уже проверенные
    global last_checked_id
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=1"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            messages = response.json()
            if messages:
                last_checked_id = messages[0]['id']
                logger.info(f"📝 Запомнил последнее сообщение: {last_checked_id}")
    except:
        pass
    
    while True:
        try:
            found = check_discord_messages()
            if found:
                logger.info("✅ Уведомление отправлено")
            time.sleep(10)
        except:
            time.sleep(30)

@app.route('/')
def home():
    return """
    <h1>🍅 УМНЫЙ мониторинг томатов</h1>
    <p>Бот проверяет только НОВЫЕ сообщения после запуска</p>
    <p>Не спамит уведомлениями о старых стоках</p>
    <p>Последнее проверенное сообщение: {}</p>
    <p><a href="/test_telegram">Тест Telegram</a> | <a href="/reset">Сбросить</a></p>
    """.format(last_checked_id or "еще не проверял")

@app.route('/test_telegram')
def test_telegram():
    success = send_telegram("✅ Умный бот работает! Жду новые томаты.")
    return f"Тест: {'✅ Отправлено' if success else '❌ Ошибка'}"

@app.route('/reset')
def reset():
    global last_checked_id
    last_checked_id = None
    return "✅ Сброшено! Будет проверять все сообщения как новые."

# Запускаем мониторинг
threading.Thread(target=monitoring_loop, daemon=True).start()

if __name__ == '__main__':
    logger.info("🚀 УМНЫЙ БОТ ЗАПУЩЕН - жду новые сообщения с томатами!")
    app.run(host='0.0.0.0', port=5000)
