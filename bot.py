from flask import Flask
import requests
import os
import time
import logging
from telethon import TelegramClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)

# Настройки
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
TARGET_BOT = '@gardenstockbot'

async def check_stock():
    """Проверяет сток у бота"""
    try:
        client = TelegramClient('session', API_ID, API_HASH)
        await client.start()
        
        bot = await client.get_entity(TARGET_BOT)
        
        async with client.conversation(bot) as conv:
            # Нажимаем кнопку "Сток"
            await conv.send_message('🌱 Сток')
            response = await conv.get_response()
            
            # Анализируем ответ
            stock_text = response.text
            logger.info(f"📊 Получен сток")
            
            # Ищем Помидор в разделе семена (ТЕСТОВЫЙ РЕЖИМ)
            if "🌱 Семена:" in stock_text:
                seeds_section = stock_text.split("🌱 Семена:")[1].split("🥚 Яйца:")[0]
                if "Помидор" in seeds_section:
                    return True, stock_text
                    
        await client.disconnect()
        return False, stock_text
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False, None

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
        logger.info("✅ Уведомление отправлено")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

def stock_monitor():
    """Основной монитор"""
    logger.info("🤖 Запускаю мониторинг @gardenstockbot...")
    send_telegram("🔍 ТЕСТ: Начинаю мониторинг стока на Помидор каждую минуту!")
    
    import asyncio
    last_found = False
    
    while True:
        try:
            # Проверяем сток
            found, stock_info = asyncio.run(check_stock())
            
            if found and not last_found:
                logger.info("🍅 ПОМИДОР НАЙДЕН! (тест успешен)")
                send_telegram("🍅 🍅 🍅 ТЕСТ УСПЕШЕН! ПОМИДОР В ПРОДАЖЕ! 🍅 🍅 🍅")
                send_telegram("✅ Система работает! Теперь можно настроить на Great Pumpkin")
                last_found = True
            elif not found:
                last_found = False
                
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            
        time.sleep(60)  # 1 минута

@app.route('/')
def home():
    return "🍅 ТЕСТ: Мониторю @gardenstockbot на предмет Помидора каждую минуту"

# Запускаем
import threading
logger.info("🚀 Запускаю тестовый монитор...")
monitor_thread = threading.Thread(target=stock_monitor)
monitor_thread.daemon = True
monitor_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
