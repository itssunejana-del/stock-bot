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

# Храним несколько последних обработанных сообщений
last_processed_messages = set()
last_notification_time = None
MAX_PROCESSED_MESSAGES = 10  # Храним последние 10 сообщений

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

def cleanup_old_messages():
    """Очищает старые сообщения из памяти"""
    global last_processed_messages
    if len(last_processed_messages) > MAX_PROCESSED_MESSAGES:
        # Оставляем только последние 5 сообщений
        last_processed_messages = set(list(last_processed_messages)[-5:])
        logger.info("🧹 Очистил старые сообщения")

def check_discord_messages():
    """Проверяет несколько последних сообщений"""
    global last_processed_messages, last_notification_time
    
    try:
        # Проверяем 5 последних сообщений
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=5"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        logger.info(f"🔍 Проверяю 5 последних сообщений...")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            logger.info(f"📨 Найдено {len(messages)} сообщений")
            
            found_seeds = []
            
            # Проверяем все сообщения от нового к старому
            for message in messages:
                message_id = message['id']
                author = message['author']['username']
                
                logger.info(f"📝 Проверяю сообщение {message_id} от {author}")
                
                # Пропускаем если уже обрабатывали
                if message_id in last_processed_messages:
                    logger.info(f"⏩ Пропускаю (уже обработано)")
                    continue
                
                # Добавляем в обработанные
                last_processed_messages.add(message_id)
                logger.info(f"✅ Добавил в обработанные: {message_id}")
                
                # Проверяем эмбады
                embeds = message.get('embeds', [])
                for embed in embeds:
                    all_embed_text = ""
                    
                    # Собираем весь текст
                    for field in embed.get('fields', []):
                        all_embed_text += f" {field.get('name', '')} {field.get('value', '')}"
                    
                    all_embed_text += f" {embed.get('description', '')} {embed.get('title', '')}"
                    
                    logger.info(f"🔍 Текст эмбада: {all_embed_text[:150]}...")
                    
                    # Ищем семена
                    seeds_to_monitor = [
                        'Tomato', 'Bamboo', 
                        'Great Pumpkin', 'Romanesco', 'Crimson Thorn'
                    ]
                    
                    for seed in seeds_to_monitor:
                        if seed in all_embed_text:
                            seed_display_name = {
                                'Tomato': 'Томат',
                                'Bamboo': 'Бамбук', 
                                'Great Pumpkin': 'Великая Тыква',
                                'Romanesco': 'Романеско',
                                'Crimson Thorn': 'Багровая Колючка'
                            }.get(seed, seed)
                            
                            if seed_display_name not in found_seeds:
                                found_seeds.append(seed_display_name)
                                logger.info(f"🎯 НАЙДЕНО: {seed_display_name}")
            
            # Отправляем уведомления для найденных семян
            if found_seeds:
                current_time = datetime.now()
                
                # Кулдаун 4.5 минуты
                if last_notification_time:
                    time_passed = current_time - last_notification_time
                    if time_passed.total_seconds() < 270:
                        logger.info("⏳ Кулдаун активен, пропускаем уведомления")
                        return False
                
                # Отправляем уведомление для каждого найденного семени
                for seed in found_seeds:
                    send_telegram(f"{seed} в стоке")
                
                last_notification_time = current_time
                return True
            
            logger.info("🔍 Семена не найдены в новых сообщениях")
            return False
            
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
        return False

@app.route('/')
def home():
    return "🍅 Мониторю 5 семян (5 последних сообщений)..."

def discord_monitor():
    """Основной мониторинг"""
    logger.info("🔄 ЗАПУСК МОНИТОРИНГА 5 СООБЩЕНИЙ")
    
    while True:
        try:
            found = check_discord_messages()
            
            if found:
                logger.info("✅ Уведомления отправлены")
            else:
                logger.info("🔍 Новых семян нет")
                
            # Очищаем старые сообщения
            cleanup_old_messages()
                
            time.sleep(10)  # Проверяем каждые 10 секунд
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            time.sleep(30)

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК С ПРОВЕРКОЙ 5 СООБЩЕНИЙ")
    
    # Запускаем мониторинг
    monitor_thread = threading.Thread(target=discord_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    app.run(host='0.0.0.0', port=5000)
