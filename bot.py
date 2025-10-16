from flask import Flask
import requests
import os
import time
import logging
import threading
import sys

# Настраиваем детальное логирование
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

def test_discord_connection():
    """ТЕСТИРУЕТ ПОДКЛЮЧЕНИЕ К DISCORD"""
    try:
        logger.info("🚀 ТЕСТ ПОДКЛЮЧЕНИЯ К DISCORD")
        
        # 1. Проверяем базовое подключение бота
        url = "https://discord.com/api/v10/users/@me"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            bot_data = response.json()
            logger.info(f"✅ БОТ ПОДКЛЮЧЕН: {bot_data['username']}")
            
            # 2. Проверяем доступ к каналу
            url_channel = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=5"
            response_channel = requests.get(url_channel, headers=headers, timeout=10)
            
            if response_channel.status_code == 200:
                messages = response_channel.json()
                logger.info(f"✅ ДОСТУП К КАНАЛУ: {len(messages)} сообщений")
                return True, f"Бот {bot_data['username']} подключен. Доступ к каналу: {len(messages)} сообщений"
            else:
                logger.error(f"❌ НЕТ ДОСТУПА К КАНАЛУ: {response_channel.status_code}")
                return False, f"Нет доступа к каналу: {response_channel.status_code}"
        else:
            logger.error(f"❌ ОШИБКА ПОДКЛЮЧЕНИЯ: {response.status_code}")
            return False, f"Ошибка подключения: {response.status_code}"
            
    except Exception as e:
        logger.error(f"💥 ОШИБКА: {e}")
        return False, f"Ошибка: {str(e)}"

def send_telegram(text):
    """Отправляет сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        response = requests.post(url, data=data, timeout=10)
        logger.info(f"📱 Telegram: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

def check_discord_messages():
    """Проверяет сообщения в канале Discord"""
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=50"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            logger.info(f"📨 Получено {len(messages)} сообщений")
            
            # Ищем Tomato в сообщениях
            for message in messages:
                content = message.get('content', '')
                
                # Проверяем текст сообщения
                if 'Tomato' in content or ':Tomato:' in content:
                    logger.info("🍅 TOMATO НАЙДЕН В ТЕКСТЕ!")
                    return True, content
                
                # Проверяем эмбады
                for embed in message.get('embeds', []):
                    embed_text = str(embed.get('description', '')) + str(embed.get('title', ''))
                    if 'Tomato' in embed_text:
                        logger.info("🍅 TOMATO НАЙДЕН В ЭМБАДЕ!")
                        return True, embed_text
            
            return False, "Tomato не найден"
        else:
            return False, f"Ошибка API: {response.status_code}"
            
    except Exception as e:
        return False, f"Ошибка: {str(e)}"

@app.route('/')
def home():
    return """
    <h1>🍅 Tomato Monitor Bot</h1>
    <p>Бот работает и мониторит канал Discord!</p>
    <p><a href="/test">🧪 Тест подключения</a></p>
    <p><a href="/status">📊 Статус</a></p>
    <p><a href="/check">🔍 Проверить сообщения</a></p>
    """

@app.route('/test')
def test_connection():
    """Страница для тестирования подключения"""
    logger.info("🧪 ЗАПУСК ТЕСТА ПОДКЛЮЧЕНИЯ")
    success, message = test_discord_connection()
    
    # Отправляем результат в Telegram
    status = "✅ УСПЕХ" if success else "❌ ОШИБКА"
    send_telegram(f"{status}: {message}")
    
    return f"""
    <h1>Результат теста подключения</h1>
    <p>Статус: <b>{status}</b></p>
    <p>Сообщение: {message}</p>
    <p><a href="/">← Назад</a></p>
    """

@app.route('/status')
def status():
    """Страница статуса"""
    success, message = test_discord_connection()
    return f"""
    <h1>📊 Статус системы</h1>
    <p>Discord: <b>{'✅ Подключен' if success else '❌ Ошибка'}</b></p>
    <p>Сообщение: {message}</p>
    <p>Telegram: ✅ Настроен</p>
    <p><a href="/">← Назад</a></p>
    """

@app.route('/check')
def check_messages():
    """Проверяет сообщения на наличие Tomato"""
    logger.info("🔍 ПРОВЕРКА СООБЩЕНИЙ")
    found, message = check_discord_messages()
    
    result = "🍅 TOMATO НАЙДЕН!" if found else "❌ Tomato не найден"
    
    if found:
        send_telegram(f"🚨 ТЕСТ: {result}")
        send_telegram(f"📋 {message[:200]}...")
    
    return f"""
    <h1>Результат проверки</h1>
    <p>Результат: <b>{result}</b></p>
    <p>Сообщение: {message[:500] if found else message}</p>
    <p><a href="/">← Назад</a></p>
    """

def discord_monitor():
    """Основной мониторинг"""
    logger.info("🔄 ЗАПУСК ОСНОВНОГО МОНИТОРИНГА")
    
    last_detected = False
    
    while True:
        try:
            found, message = check_discord_messages()
            
            if found and not last_detected:
                logger.info("🎯 TOMATO ОБНАРУЖЕН - ОТПРАВЛЯЮ УВЕДОМЛЕНИЕ!")
                send_telegram("🚨 TOMATO В ПРОДАЖЕ! 🍅")
                send_telegram(f"📋 {message}")
                last_detected = True
            elif not found:
                last_detected = False
                
            time.sleep(30)  # Проверяем каждые 30 секунд
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            time.sleep(60)

# Запускаем приложение
if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК СИСТЕМЫ")
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=discord_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # Отправляем уведомление о запуске
    send_telegram("🔍 Бот запущен! Начинаю мониторинг Tomato...")
    
    app.run(host='0.0.0.0', port=5000)
