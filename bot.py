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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Логируем переменные окружения (без токенов)
logger.info("🔧 ПРОВЕРКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ:")
logger.info(f"📝 TELEGRAM_TOKEN: {'ЕСТЬ' if os.getenv('TELEGRAM_TOKEN') else 'НЕТ'}")
logger.info(f"📝 TELEGRAM_CHAT_ID: {'ЕСТЬ' if os.getenv('TELEGRAM_CHAT_ID') else 'НЕТ'}")
logger.info(f"📝 DISCORD_TOKEN: {'ЕСТЬ' if os.getenv('DISCORD_TOKEN') else 'НЕТ'}")
logger.info(f"📝 DISCORD_CHANNEL_ID: {'ЕСТЬ' if os.getenv('DISCORD_CHANNEL_ID') else 'НЕТ'}")

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

def test_discord_connection():
    """ТЕСТИРУЕТ ПОДКЛЮЧЕНИЕ К DISCORD С ДЕТАЛЬНЫМ ЛОГИРОВАНИЕМ"""
    try:
        logger.info("🚀 НАЧИНАЮ ТЕСТ ПОДКЛЮЧЕНИЯ К DISCORD")
        
        # Проверяем базовое подключение бота
        url = "https://discord.com/api/v10/users/@me"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        logger.debug(f"🔗 URL: {url}")
        logger.debug(f"📝 Заголовки: Authorization: Bot {DISCORD_TOKEN[:15]}...")
        
        response = requests.get(url, headers=headers, timeout=10)
        
        logger.info(f"📡 ОТВЕТ DISCORD API:")
        logger.info(f"   Статус: {response.status_code}")
        logger.info(f"   Текст: {response.text[:200]}...")
        
        if response.status_code == 200:
            bot_data = response.json()
            logger.info(f"✅ БОТ УСПЕШНО ПОДКЛЮЧЕН:")
            logger.info(f"   Имя: {bot_data['username']}#{bot_data['discriminator']}")
            logger.info(f"   ID: {bot_data['id']}")
            return True, "Бот подключен"
        else:
            logger.error(f"❌ ОШИБКА ПОДКЛЮЧЕНИЯ: {response.status_code}")
            return False, f"Ошибка {response.status_code}: {response.text}"
            
    except requests.exceptions.Timeout:
        logger.error("⏰ ТАЙМАУТ ПОДКЛЮЧЕНИЯ К DISCORD")
        return False, "Таймаут подключения"
    except requests.exceptions.ConnectionError:
        logger.error("🌐 ОШИБКА СОЕДИНЕНИЯ С DISCORD")
        return False, "Ошибка соединения"
    except Exception as e:
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {str(e)}", exc_info=True)
        return False, f"Критическая ошибка: {str(e)}"

def send_telegram(text):
    """Отправляет сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        response = requests.post(url, data=data, timeout=10)
        logger.info(f"📱 Telegram ответ: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

@app.route('/')
def home():
    return "🍅 Мониторю канал на предмет Tomato"

@app.route('/test')
def test():
    """Страница для тестирования подключения"""
    logger.info("🧪 ЗАПУСК ТЕСТА ПОДКЛЮЧЕНИЯ")
    success, message = test_discord_connection()
    
    # Отправляем результат в Telegram
    status = "✅ УСПЕХ" if success else "❌ ОШИБКА"
    send_telegram(f"{status}: {message}")
    
    return f"""
    <h1>Результат теста</h1>
    <p>Статус: <b>{status}</b></p>
    <p>Сообщение: {message}</p>
    <p>Проверьте логи в Render для деталей</p>
    """

def start_monitoring():
    """Запускает мониторинг после теста"""
    logger.info("🔄 ЗАПУСК МОНИТОРИНГА...")
    # Здесь будет основной код мониторинга
    
    # Тестовый цикл
    while True:
        success, message = test_discord_connection()
        if success:
            logger.info("🎯 Бот работает, можно начинать мониторинг")
            break
        else:
            logger.error("🔄 Повторная попытка через 30 секунд...")
            time.sleep(30)

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК ПРИЛОЖЕНИЯ")
    
    # Запускаем тест подключения
    success, message = test_discord_connection()
    
    if success:
        send_telegram("✅ Бот успешно подключен к Discord!")
        logger.info("✅ Начинаем мониторинг")
        monitor_thread = threading.Thread(target=start_monitoring)
        monitor_thread.daemon = True
        monitor_thread.start()
    else:
        send_telegram(f"❌ Ошибка подключения: {message}")
        logger.error("❌ Невозможно начать мониторинг из-за ошибки подключения")
    
    app.run(host='0.0.0.0', port=5000)
