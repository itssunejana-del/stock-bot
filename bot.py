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

# Храним время последнего сообщения вместо ID
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
            logger.error(f"❌ Ошибка Telegram: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")
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
    global last_message_time, processed_messages
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=10"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            logger.info(f"📨 Получено {len(messages)} сообщений")
            
            found_tomato = False
            
            for message in messages:
                message_id = message['id']
                author = message.get('author', {}).get('username', 'Unknown')
                
                # Только сообщения Вулкана
                if 'Vulcan' not in author:
                    continue
                
                message_time = get_message_time(message)
                full_text = get_full_message_text(message)
                
                logger.info(f"🔍 Сообщение {message_id}: {full_text[:80]}...")
                
                # Проверяем время сообщения - только свежие (последние 10 минут)
                current_time = datetime.now().replace(tzinfo=message_time.tzinfo)
                time_diff = (current_time - message_time).total_seconds()
                
                if time_diff > 600:  # 10 минут
                    logger.info("⏩ Пропускаем старое сообщение")
                    continue
                
                # Проверяем, новое ли сообщение
                if message_id in processed_messages:
                    logger.info("⏩ Уже обрабатывали это сообщение")
                    continue
                
                processed_messages.add(message_id)
                
                # Ищем ТОМАТ
                if 'Tomato' in full_text or 'To...' in full_text:
                    logger.info("🎯 ОБНАРУЖЕН ТОМАТ В НОВОМ СООБЩЕНИИ!")
                    send_telegram("🍅 Томат в стоке!")
                    found_tomato = True
                    # Не прерываем цикл - может быть несколько новых сообщений
            
            # Очищаем старые сообщения из памяти
            if len(processed_messages) > 100:
                processed_messages = set()
                logger.info("🧹 Очистил историю сообщений")
            
            return found_tomato
        else:
            logger.error(f"❌ Ошибка Discord: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        return False

def monitoring_loop():
    logger.info("🔄 ЗАПУСК УЛУЧШЕННОГО МОНИТОРИНГА")
    
    while True:
        try:
            found = check_discord_messages()
            if found:
                logger.info("✅ Уведомление отправлено")
            else:
                logger.info("🔍 Новых томатов нет")
            
            time.sleep(15)  # Проверка каждые 15 секунд
            
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле: {e}")
            time.sleep(30)

@app.route('/')
def home():
    return """
    <h1>🍅 УЛУЧШЕННЫЙ мониторинг томатов</h1>
    <p>Бот проверяет сообщения за последние 10 минут</p>
    <p>Не зависит от ID сообщений, работает по времени</p>
    <p>Обработано сообщений: {}</p>
    <p><a href="/test">Тест сейчас</a> | <a href="/reset">Сбросить</a></p>
    """.format(len(processed_messages))

@app.route('/test')
def test():
    """Принудительная проверка"""
    result = check_discord_messages()
    return f"Проверка: {'🎯 Томат найден!' if result else '🔍 Томатов нет'}"

@app.route('/reset')
def reset():
    """Сброс истории сообщений"""
    global processed_messages
    processed_messages = set()
    logger.info("🔄 Сброшена история сообщений")
    return "✅ История сброшена! Будет проверять все сообщения как новые."

# Запускаем мониторинг
threading.Thread(target=monitoring_loop, daemon=True).start()

if __name__ == '__main__':
    logger.info("🚀 УЛУЧШЕННЫЙ БОТ ЗАПУЩЕН!")
    app.run(host='0.0.0.0', port=5000)
