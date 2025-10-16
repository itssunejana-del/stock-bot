from flask import Flask
import requests
import os
import time
import logging
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
        logger.info("✅ Уведомление отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

def check_discord_connection():
    """Проверяет подключение к Discord API и ищет Tomato в эмбадах"""
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=100"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            messages = response.json()
            logger.info(f"📨 Получено сообщений: {len(messages)}")
            
            # 🔍 ПРОВЕРЯЕМ ЭМБАДЫ В СООБЩЕНИЯХ
            for i, message in enumerate(messages[:5]):
                logger.info(f"📝 Сообщение {i}:")
                logger.info(f"   📄 Текст: '{message.get('content', 'НЕТ ТЕКСТА')}'")
                logger.info(f"   🎨 Эмбадов: {len(message.get('embeds', []))}")
                
                # Проверяем эмбады
                for j, embed in enumerate(message.get('embeds', [])):
                    embed_description = embed.get('description', '')
                    logger.info(f"   📋 Эмбад {j}: '{embed_description[:100]}...'")
                    
                    # Ищем Tomato в описании эмбада
                    if 'Tomato' in embed_description:
                        logger.info(f"🍅 TOMATO НАЙДЕН В ЭМБАДЕ!")
                        return True, embed_description
            
            logger.info("❌ Tomato не найден в последних 100 сообщениях")
            return False, None
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            return False, None
            
    except Exception as e:
        logger.error(f"❌ Ошибка подключения: {e}")
        return False, None

def discord_monitor():
    """Мониторит канал Discord"""
    logger.info("🚀 ЗАПУСКАЮ DSCORD МОНИТОР...")
    
    # Тестовое подключение
    success, message = check_discord_connection()
    
    if success:
        send_telegram("✅ Discord подключение успешно! Мониторю Tomato...")
        logger.info("🔍 Начинаю мониторинг Tomato...")
    else:
        send_telegram("❌ Tomato не найден в истории сообщений")
        logger.info("🔍 Продолжаю мониторинг...")
    
    last_detected = False
    
    while True:
        try:
            found, message = check_discord_connection()
            
            if found and not last_detected:
                logger.info("🍅 TOMATO ОБНАРУЖЕН!")
                send_telegram("🍅 TOMATO В ПРОДАЖЕ! 🍅")
                send_telegram(f"📋 {message}")
                last_detected = True
            elif not found:
                last_detected = False
                
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            
        time.sleep(30)

@app.route('/')
def home():
    return "🍅 Мониторю канал на предмет Tomato"

# Запускаем монитор
logger.info("🚀 Запускаю систему...")
send_telegram("🔍 Бот запущен! Проверяю историю сообщений...")
monitor_thread = threading.Thread(target=discord_monitor)
monitor_thread.daemon = True
monitor_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
