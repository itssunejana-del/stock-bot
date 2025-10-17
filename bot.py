from flask import Flask
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

# Храним последние версии сообщений
message_versions = {}
last_notification_time = None
CHECK_INTERVAL = 10  # секунд

def send_telegram(text):
    """Отправляет сообщение в Telegram"""
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
        logger.error(f"❌ Ошибка подключения Telegram: {e}")
        return False

def self_ping():
    """Само-пинг чтобы Render не засыпал"""
    try:
        requests.get(f"https://stock-bot-cj4s.onrender.com/", timeout=5)
    except:
        pass

def get_message_content(message):
    """Извлекает весь текст из сообщения"""
    content = message.get('content', '')
    embeds = message.get('embeds', [])
    
    all_text = content
    
    for embed in embeds:
        all_text += f" {embed.get('title', '')}"
        all_text += f" {embed.get('description', '')}"
        all_text += f" {embed.get('footer', {}).get('text', '')}"
        
        for field in embed.get('fields', []):
            all_text += f" {field.get('name', '')}"
            all_text += f" {field.get('value', '')}"
    
    return all_text

def check_for_seeds_changes():
    """Проверяет изменения в сообщениях Вулкана"""
    global message_versions, last_notification_time
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=20"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            messages = response.json()
            found_changes = []
            
            logger.info(f"🔍 Проверяю {len(messages)} сообщений на изменения...")
            
            for message in messages:
                message_id = message['id']
                author = message.get('author', {}).get('username', '')
                
                # Фильтруем только сообщения Вулкана
                if 'Vulcan' not in author:
                    continue
                
                current_content = get_message_content(message)
                
                # Если сообщение новое - сохраняем его
                if message_id not in message_versions:
                    message_versions[message_id] = current_content
                    logger.info(f"📝 Новое сообщение Вулкана: {message_id}")
                    continue
                
                # Проверяем изменения
                previous_content = message_versions[message_id]
                if current_content != previous_content:
                    logger.info(f"🔄 Обнаружено изменение в сообщении {message_id}!")
                    message_versions[message_id] = current_content
                    
                    # Ищем семена в измененном сообщении
                    seeds_found = analyze_seeds_in_text(current_content)
                    if seeds_found:
                        found_changes.extend(seeds_found)
                        logger.info(f"🎯 Найдены семена после изменения: {seeds_found}")
            
            # Отправляем уведомления об изменениях
            if found_changes:
                current_time = datetime.utcnow()
                
                # Кулдаун 4.5 минуты
                if last_notification_time:
                    time_passed = current_time - last_notification_time
                    if time_passed.total_seconds() < 270:
                        logger.info("⏳ Кулдаун активен, пропускаем уведомление")
                        return False
                
                # Отправляем уведомления
                for seed in found_changes:
                    send_telegram(f"{seed} в стоке (обновление)")
                
                last_notification_time = current_time
                return True
            
            return False
            
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Ошибка при проверке изменений: {e}")
        return False

def analyze_seeds_in_text(text):
    """Анализирует текст на наличие семян"""
    seeds_found = []
    
    # Список для поиска
    seed_patterns = [
        ('Tomato', 'Томат'),
        ('Bamboo', 'Бамбук'),
        ('Great Pumpkin', 'Великая Тыква'),
        ('Romanesco', 'Романеско'),
        ('Crimson Thorn', 'Багровая Колючка'),
        ('Carrot', 'Морковь'),
        ('Strawberry', 'Клубника'),
        ('SEEDS STOCK', 'Сток семян')
    ]
    
    for eng_name, rus_name in seed_patterns:
        if eng_name in text:
            seeds_found.append(rus_name)
            logger.info(f"🌱 Обнаружен {rus_name} в тексте")
    
    return seeds_found

def cleanup_old_messages():
    """Очищает старые сообщения из памяти"""
    global message_versions
    if len(message_versions) > 50:
        # Оставляем только 30 самых новых сообщений
        all_ids = list(message_versions.keys())
        if len(all_ids) > 30:
            ids_to_remove = all_ids[:-30]
            for msg_id in ids_to_remove:
                del message_versions[msg_id]
            logger.info(f"🧹 Очищено {len(ids_to_remove)} старых сообщений")

@app.route('/')
def home():
    return "🍅 Мониторю ИЗМЕНЕНИЯ сообщений Вулкана..."

@app.route('/status')
def status():
    return f"📊 Отслеживаю {len(message_versions)} сообщений Вулкана"

@app.route('/reset')
def reset():
    """Сбрасывает историю сообщений"""
    global message_versions
    message_versions = {}
    return "✅ История сообщений сброшена! Начинаю отслеживание заново."

def uptime_monitor():
    """Поддерживает сервер активным"""
    while True:
        self_ping()
        time.sleep(600)

def discord_monitor():
    """Основной мониторинг изменений"""
    logger.info("🔄 ЗАПУСК МОНИТОРИНГА ИЗМЕНЕНИЙ СООБЩЕНИЙ ВУЛКАНА")
    
    while True:
        try:
            changes_found = check_for_seeds_changes()
            
            if changes_found:
                logger.info("✅ Уведомления об изменениях отправлены")
            else:
                logger.info("🔍 Изменений не обнаружено")
            
            cleanup_old_messages()
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            time.sleep(30)

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК СИСТЕМЫ МОНИТОРИНГА ИЗМЕНЕНИЙ")
    
    threading.Thread(target=discord_monitor, daemon=True).start()
    threading.Thread(target=uptime_monitor, daemon=True).start()
    
    app.run(host='0.0.0.0', port=5000)
