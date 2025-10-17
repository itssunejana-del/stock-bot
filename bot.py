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

# Простые переменные
last_processed_message_id = None
last_notification_time = None

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
            logger.error(f"❌ Ошибка Telegram: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")
        return False

def check_discord_messages():
    """Проверяет последнее сообщение в канале"""
    global last_processed_message_id, last_notification_time
    
    try:
        # Проверяем только 1 последнее сообщение
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=1"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        logger.info(f"🔍 Проверяю канал {DISCORD_CHANNEL_ID}...")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            
            if not messages:
                return False, "Нет сообщений", None
            
            message = messages[0]
            message_id = message['id']
            author = message['author']['username']
            
            logger.info(f"📨 Последнее сообщение от {author}: {message_id}")
            
            # Пропускаем если уже обрабатывали
            if message_id == last_processed_message_id:
                return False, "Уже обработано", message_id
            
            # Проверяем эмбады
            embeds = message.get('embeds', [])
            for embed in embeds:
                all_embed_text = ""
                
                # Собираем весь текст
                for field in embed.get('fields', []):
                    all_embed_text += f" {field.get('name', '')} {field.get('value', '')}"
                
                all_embed_text += f" {embed.get('description', '')} {embed.get('title', '')}"
                
                logger.info(f"🔍 Текст эмбада: {all_embed_text[:100]}...")
                
                # Ищем семена
                seeds_to_monitor = [
                    'Tomato', 'Bamboo', 
                    'Great Pumpkin', 'Romanesco', 'Crimson Thorn'
                ]
                
                found_seeds = []
                for seed in seeds_to_monitor:
                    if seed in all_embed_text:
                        found_seeds.append(seed)
                        logger.info(f"🎯 НАЙДЕНО: {seed}")
                
                if found_seeds:
                    current_time = datetime.now()
                    
                    # Кулдаун 4.5 минуты
                    if last_notification_time:
                        time_passed = current_time - last_notification_time
                        if time_passed.total_seconds() < 270:
                            logger.info("⏳ Кулдаун активен")
                            last_processed_message_id = message_id
                            return False, "Кулдаун", message_id
                    
                    # Отправляем уведомление для первого найденного семени
                    seed_name = found_seeds[0]
                    seed_display_name = {
                        'Tomato': 'Томат',
                        'Bamboo': 'Бамбук', 
                        'Great Pumpkin': 'Великая Тыква',
                        'Romanesco': 'Романеско',
                        'Crimson Thorn': 'Багровая Колючка'
                    }.get(seed_name, seed_name)
                    
                    last_notification_time = current_time
                    last_processed_message_id = message_id
                    
                    return True, f"{seed_display_name} в стоке", message_id
            
            last_processed_message_id = message_id
            return False, "Семена не найдены", message_id
            
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            return False, f"API ошибка: {response.status_code}", None
            
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        return False, f"Ошибка: {str(e)}", None

@app.route('/')
def home():
    return "🍅 Мониторю 5 семян: Томат, Бамбук, Великая Тыква, Романеско, Багровая Колючка"

def discord_monitor():
    """Основной мониторинг"""
    logger.info("🔄 ЗАПУСК МОНИТОРИНГА 5 СЕМЯН")
    
    while True:
        try:
            found, message, message_id = check_discord_messages()
            
            if found:
                logger.info(f"🎯 ОТПРАВЛЯЮ: {message}")
                success = send_telegram(message)
                if success:
                    logger.info("✅ Уведомление отправлено")
                else:
                    logger.error("❌ Ошибка отправки")
            else:
                logger.info(f"🔍 {message}")
                
            time.sleep(10)  # Проверяем каждые 10 секунд
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            time.sleep(30)

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК ПРОСТОЙ СИСТЕМЫ")
    
    # Запускаем мониторинг
    monitor_thread = threading.Thread(target=discord_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    app.run(host='0.0.0.0', port=5000)
