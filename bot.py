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

# Проверяем переменные
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

logger.info("🔧 Проверка переменных окружения...")
logger.info(f"TELEGRAM_TOKEN: {'✅' if TELEGRAM_TOKEN else '❌'}")
logger.info(f"TELEGRAM_CHAT_ID: {'✅' if TELEGRAM_CHAT_ID else '❌'}")
logger.info(f"DISCORD_TOKEN: {'✅' if DISCORD_TOKEN else '❌'}")
logger.info(f"DISCORD_CHANNEL_ID: {'✅' if DISCORD_CHANNEL_ID else '❌'}")

# Для хранения обработанных сообщений
processed_messages = set()

def send_telegram(text):
    """Отправляет сообщение в Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ Не настроен Telegram")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено в Telegram: {text}")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def check_discord_messages():
    """Проверяет сообщения в Discord канале"""
    if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID:
        logger.error("❌ Не настроен Discord")
        return False
        
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=10"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        logger.info("🔍 Запрос к Discord API...")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            logger.info(f"📨 Получено {len(messages)} сообщений из Discord")
            
            for message in messages:
                message_id = message['id']
                author = message.get('author', {}).get('username', 'Unknown')
                content = message.get('content', '')[:200]  # Первые 200 символов
                
                # Логируем все сообщения от Вулкана
                if 'Vulcan' in author:
                    logger.info(f"👤 Сообщение от {author}: {content}...")
                    
                    # Проверяем, новое ли сообщение
                    if message_id not in processed_messages:
                        logger.info(f"🆕 НОВОЕ сообщение Вулкана! ID: {message_id}")
                        processed_messages.add(message_id)
                        
                        # Ищем ключевые слова
                        if any(word in content for word in ['Tomato', 'Carrot', 'Strawberry', 'SEEDS', 'STOCK']):
                            logger.info("🎯 ОБНАРУЖЕНЫ СЕМЕНА!")
                            send_telegram(f"🎯 Обнаружены семена в стоке! Проверь Discord.")
                            return True
            
            return False
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            if response.status_code == 401:
                logger.error("❌ Неверный Discord токен!")
            elif response.status_code == 403:
                logger.error("❌ Нет доступа к каналу!")
            elif response.status_code == 404:
                logger.error("❌ Канал не найден!")
            return False
            
    except Exception as e:
        logger.error(f"💥 Ошибка при проверке Discord: {e}")
        return False

def monitoring_loop():
    """Основной цикл мониторинга"""
    logger.info("🔄 Запуск цикла мониторинга Discord...")
    
    while True:
        try:
            check_discord_messages()
            time.sleep(30)  # Проверка каждые 30 секунд
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле мониторинга: {e}")
            time.sleep(60)

@app.route('/')
def home():
    logger.info("✅ Кто-то зашел на главную страницу")
    return """
    <h1>🍅 Мониторинг семян работает!</h1>
    <p>Проверяю Discord каждые 30 секунд</p>
    <p><a href="/test">Тест Discord</a> | <a href="/test_telegram">Тест Telegram</a></p>
    <p>Обработано сообщений: {}</p>
    """.format(len(processed_messages))

@app.route('/test')
def test_discord():
    """Тест подключения к Discord"""
    logger.info("🧪 Тест Discord API")
    result = check_discord_messages()
    return f"Тест Discord: {'✅ Успешно' if result else '❌ Ошибка или семена не найдены'}"

@app.route('/test_telegram')
def test_telegram():
    """Тест отправки в Telegram"""
    logger.info("🧪 Тест Telegram")
    success = send_telegram("🔔 Тестовое сообщение от бота - система работает!")
    return f"Тест Telegram: {'✅ Отправлено' if success else '❌ Ошибка'}"

@app.route('/reset')
def reset():
    """Сброс обработанных сообщений"""
    global processed_messages
    processed_messages = set()
    logger.info("🔄 Сброшены обработанные сообщения")
    return "✅ Сброс выполнен! Бот будет проверять все сообщения заново."

# Запускаем мониторинг в фоне
threading.Thread(target=monitoring_loop, daemon=True).start()

if __name__ == '__main__':
    logger.info("🚀 БОТ ЗАПУЩЕН И НАЧИНАЕТ МОНИТОРИНГ!")
    app.run(host='0.0.0.0', port=5000)
