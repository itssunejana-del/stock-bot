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

# Храним ВСЕ обработанные сообщения
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

def check_discord_messages():
    global processed_messages
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=20"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            logger.info(f"📨 Получено {len(messages)} сообщений")
            
            found_tomato = False
            new_messages_count = 0
            
            for message in messages:
                message_id = message['id']
                author = message.get('author', {}).get('username', 'Unknown')
                
                # Только сообщения Вулкана
                if 'Vulcan' not in author:
                    continue
                
                full_text = get_full_message_text(message)
                
                # Проверяем, новое ли сообщение
                if message_id in processed_messages:
                    continue  # Уже обрабатывали
                
                new_messages_count += 1
                processed_messages.add(message_id)
                
                logger.info(f"🆕 НОВОЕ сообщение {message_id}: {full_text[:100]}...")
                
                # Ищем ТОМАТ
                if 'Tomato' in full_text or 'To...' in full_text:
                    logger.info("🎯 ОБНАРУЖЕН ТОМАТ В НОВОМ СООБЩЕНИИ!")
                    send_telegram("🍅 Томат в стоке!")
                    found_tomato = True
            
            logger.info(f"🔍 Найдено {new_messages_count} новых сообщений")
            
            # Очищаем старые сообщения из памяти (оставляем последние 200)
            if len(processed_messages) > 200:
                # Преобразуем в список, возьмем последние 100, и обратно в set
                all_messages = list(processed_messages)
                processed_messages = set(all_messages[-100:])
                logger.info("🧹 Очистил историю сообщений")
            
            return found_tomato
        else:
            logger.error(f"❌ Ошибка Discord: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        return False

def monitoring_loop():
    logger.info("🔄 ЗАПУСК ПРОСТОГО И НАДЕЖНОГО МОНИТОРИНГА")
    
    # При старте запоминаем текущие сообщения как уже обработанные
    global processed_messages
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=50"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            messages = response.json()
            for message in messages:
                if 'Vulcan' in message.get('author', {}).get('username', ''):
                    processed_messages.add(message['id'])
            logger.info(f"📝 Запомнил {len(processed_messages)} существующих сообщений")
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации: {e}")
    
    while True:
        try:
            found = check_discord_messages()
            if found:
                logger.info("✅ Уведомление отправлено")
            else:
                logger.info("🔍 Новых томатов нет")
            
            time.sleep(30)  # Проверка каждые 30 секунд
            
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле: {e}")
            time.sleep(60)

@app.route('/')
def home():
    return """
    <h1>🍅 ПРОСТОЙ И НАДЕЖНЫЙ мониторинг</h1>
    <p>Бот проверяет ВСЕ новые сообщения Вулкана</p>
    <p>Не пропускает стоки из-за временных ограничений</p>
    <p>Обработано сообщений: {}</p>
    <p><a href="/test">Тест сейчас</a> | <a href="/reset">Сбросить всё</a></p>
    """.format(len(processed_messages))

@app.route('/test')
def test():
    """Принудительная проверка"""
    result = check_discord_messages()
    return f"Проверка: {'🎯 Томат найден!' if result else '🔍 Томатов нет'}"

@app.route('/reset')
def reset():
    """Полный сброс"""
    global processed_messages
    processed_messages = set()
    logger.info("🔄 ПОЛНЫЙ СБРОС! Буду проверять все сообщения как новые.")
    return "✅ Полный сброс! Бот будет проверять ВСЕ сообщения как новые."

# Запускаем мониторинг
threading.Thread(target=monitoring_loop, daemon=True).start()

if __name__ == '__main__':
    logger.info("🚀 ПРОСТОЙ И НАДЕЖНЫЙ БОТ ЗАПУЩЕН!")
    app.run(host='0.0.0.0', port=5000)
