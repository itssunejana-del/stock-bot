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

# Переменные для работы
last_processed_messages = set()
last_notification_time = None
MAX_MESSAGE_AGE = 900  # 15 минут
MESSAGE_LIMIT = 200

def send_telegram(text):
    """Отправляет КОРОТКОЕ сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено: {text}")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram")
            return False
    except:
        logger.error(f"❌ Ошибка подключения")
        return False

def self_ping():
    """Само-пинг чтобы Render не засыпал"""
    try:
        requests.get(f"https://stock-bot-cj4s.onrender.com/", timeout=5)
    except:
        pass

def cleanup_old_messages():
    """Очищает старые сообщения из памяти"""
    global last_processed_messages
    if len(last_processed_messages) > 1000:
        last_processed_messages = set(list(last_processed_messages)[-500:])
        logger.info("🧹 Очистил старые сообщения")

def check_discord_messages():
    """Проверяет ВСЕ сообщения за последние 15 минут"""
    global last_processed_messages, last_notification_time
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit={MESSAGE_LIMIT}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            messages = response.json()
            current_time = datetime.now()
            found_plants = []
            
            # Список семян для мониторинга
            plants_to_monitor = [
                # Текущие
                'Tomato', ':Tomato:',
                'Bamboo', ':Bamboo:',
                # Новые редкие семена
                'Great Pumpkin', ':GreatPumpkin:',
                'Romanesco', ':Romanesco:',
                'Crimson Thorn', ':CrimsonThorn:',
            ]
            
            for message in messages:
                message_id = message['id']
                
                # Проверяем время сообщения
                message_time = datetime.fromisoformat(message['timestamp'].replace('Z', '+00:00'))
                time_diff = (current_time - message_time).total_seconds()
                
                if time_diff > MAX_MESSAGE_AGE:
                    continue
                
                if message_id in last_processed_messages:
                    continue
                
                last_processed_messages.add(message_id)
                
                # Проверяем эмбады
                embeds = message.get('embeds', [])
                for embed in embeds:
                    all_embed_text = ""
                    
                    for field in embed.get('fields', []):
                        all_embed_text += f" {field.get('name', '')} {field.get('value', '')}"
                    
                    all_embed_text += f" {embed.get('description', '')} {embed.get('title', '')}"
                    
                    # Ищем растения в тексте
                    for plant in plants_to_monitor:
                        if plant in all_embed_text:
                            plant_name = clean_plant_name(plant)
                            if plant_name not in found_plants:
                                found_plants.append(plant_name)
                                logger.info(f"🎯 НАЙДЕНО: {plant_name}")
            
            # Отправляем уведомления
            if found_plants:
                current_time = datetime.now()
                
                # Кулдаун 4.5 минуты
                if last_notification_time:
                    time_passed = current_time - last_notification_time
                    if time_passed.total_seconds() < 270:
                        logger.info("⏳ Кулдаун активен, пропускаем")
                        return False
                
                # Отправляем уведомление для каждого растения
                for plant in found_plants:
                    send_telegram(f"{plant} в стоке")
                
                last_notification_time = current_time
                return True
            
            return False
            
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Ошибка при проверке: {e}")
        return False

def clean_plant_name(plant):
    """Очищает название растения"""
    clean_name = plant.replace(':', '')
    
    # Русские названия для удобства
    name_mapping = {
        'Tomato': 'Томат',
        'Bamboo': 'Бамбук',
        'Great Pumpkin': 'Великая Тыква',
        'Romanesco': 'Романеско',
        'Crimson Thorn': 'Багровая Колючка'
    }
    
    return name_mapping.get(clean_name, clean_name)

@app.route('/')
def home():
    return "🍅 Мониторю 5 видов семян (15-минутное окно)..."

def uptime_monitor():
    """Поддерживает сервер активным"""
    while True:
        self_ping()
        time.sleep(600)

def discord_monitor():
    """Основной мониторинг"""
    logger.info("🔄 МОНИТОРЮ 5 СЕМЯН: Томат, Бамбук, Великая Тыква, Романеско, Багровая Колючка")
    
    while True:
        try:
            found = check_discord_messages()
            
            if found:
                logger.info("✅ Уведомления отправлены")
            else:
                logger.info("🔍 Новых семян нет")
                
            cleanup_old_messages()
            time.sleep(10)
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            time.sleep(30)

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК С МОНИТОРИНГОМ 5 СЕМЯН")
    
    threading.Thread(target=discord_monitor, daemon=True).start()
    threading.Thread(target=uptime_monitor, daemon=True).start()
    
    app.run(host='0.0.0.0', port=5000)
