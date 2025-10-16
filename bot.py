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

# Храним время последнего уведомления для каждого сообщения
last_notification_times = {}
# Время в течение которого не отправляем повторные уведомления для того же сообщения
NOTIFICATION_COOLDOWN = timedelta(minutes=4)  # 4 минуты - меньше чем интервал Vulcan

def send_telegram(text):
    """Отправляет сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        response = requests.post(url, data=data, timeout=10)
        logger.info(f"📱 Telegram отправлено: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")
        return False

def check_discord_messages():
    """Проверяет сообщения и эмбады в канале Discord"""
    global last_notification_times
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=3"  # Только 3 последних
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            current_time = datetime.now()
            
            # Ищем самое новое сообщение с Tomato
            for message in messages:
                message_id = message['id']
                author = message['author']['username']
                content = message.get('content', '')
                embeds = message.get('embeds', [])
                
                # Проверяем эмбады на наличие Tomato
                for embed in embeds:
                    # Собираем весь текст из эмбада
                    all_embed_text = ""
                    
                    # Добавляем поля эмбада
                    for field in embed.get('fields', []):
                        all_embed_text += f" {field.get('name', '')} {field.get('value', '')}"
                    
                    # Добавляем описание и заголовок
                    all_embed_text += f" {embed.get('description', '')} {embed.get('title', '')}"
                    
                    # Ищем Tomato в любом виде
                    if any(tomato_keyword in all_embed_text for tomato_keyword in ['Tomato', ':Tomato:', '🍅']):
                        logger.info(f"🎯 TOMATO НАЙДЕН В СООБЩЕНИИ {message_id}!")
                        
                        # Проверяем кулдаун для этого сообщения
                        last_notification_time = last_notification_times.get(message_id)
                        
                        if last_notification_time and (current_time - last_notification_time) < NOTIFICATION_COOLDOWN:
                            logger.info(f"⏳ Пропускаем уведомление для {message_id} - кулдаун еще активен")
                            return False, "Кулдаун активен", message_id
                        
                        # Формируем сообщение для Telegram
                        telegram_message = f"🚨 TOMATO В ПРОДАЖЕ! 🍅\n\n"
                        
                        # Добавляем информацию из эмбада
                        for field in embed.get('fields', []):
                            field_name = field.get('name', '')
                            field_value = field.get('value', '')
                            if field_name and field_value:
                                telegram_message += f"• {field_name}: {field_value}\n"
                        
                        # Обновляем время последнего уведомления для этого сообщения
                        last_notification_times[message_id] = current_time
                        logger.info(f"✅ Установлен кулдаун для сообщения {message_id}")
                        
                        return True, telegram_message, message_id
            
            return False, "Tomato не найден в новых сообщениях", None
            
        else:
            return False, f"Ошибка API: {response.status_code}", None
            
    except Exception as e:
        logger.error(f"💥 Ошибка при проверке сообщений: {e}")
        return False, f"Ошибка: {str(e)}", None

@app.route('/')
def home():
    return """
    <h1>🍅 Tomato Monitor Bot</h1>
    <p>Бот работает и мониторит канал Discord!</p>
    <p>Активные кулдауны: <b id="cooldowns">Загрузка...</b></p>
    <p><a href="/check">🔍 Проверить сообщения</a></p>
    <p><a href="/reset">🔄 Сбросить все кулдауны</a></p>
    <script>
        fetch('/cooldowns').then(r => r.text()).then(msg => {
            document.getElementById('cooldowns').textContent = msg;
        });
    </script>
    """

@app.route('/check')
def check_messages():
    """Проверяет сообщения"""
    found, message, msg_id = check_discord_messages()
    
    result = "🍅 TOMATO НАЙДЕН!" if found else "❌ Tomato не найден"
    
    return f"""
    <h1>Результат проверки</h1>
    <p>Результат: <b>{result}</b></p>
    <p>ID сообщения: {msg_id or 'Нет'}</p>
    <p>Сообщение: {message}</p>
    <p><a href="/">← Назад</a></p>
    """

@app.route('/reset')
def reset_cooldowns():
    """Сбрасывает все кулдауны"""
    global last_notification_times
    last_notification_times = {}
    return """
    <h1>🔄 Все кулдауны сброшены!</h1>
    <p>Бот будет отправлять уведомления для всех сообщений.</p>
    <p><a href="/">← Назад</a></p>
    """

@app.route('/cooldowns')
def get_cooldowns():
    """Возвращает активные кулдауны"""
    global last_notification_times
    current_time = datetime.now()
    
    active_cooldowns = []
    for msg_id, last_time in last_notification_times.items():
        time_left = NOTIFICATION_COOLDOWN - (current_time - last_time)
        if time_left.total_seconds() > 0:
            minutes_left = int(time_left.total_seconds() / 60)
            seconds_left = int(time_left.total_seconds() % 60)
            active_cooldowns.append(f"{msg_id[:10]}... ({minutes_left}м {seconds_left}с)")
    
    return ", ".join(active_cooldowns) if active_cooldowns else "Нет активных кулдаунов"

def discord_monitor():
    """Основной мониторинг"""
    logger.info("🔄 ЗАПУСК МОНИТОРИНГА С КУЛДАУНОМ")
    
    while True:
        try:
            found, message, message_id = check_discord_messages()
            
            if found:
                logger.info(f"🎯 ОТПРАВЛЯЮ УВЕДОМЛЕНИЕ ДЛЯ СООБЩЕНИЯ {message_id}!")
                success = send_telegram(message)
                if success:
                    logger.info("✅ Уведомление успешно отправлено в Telegram!")
                else:
                    logger.error("❌ Не удалось отправить уведомление в Telegram")
            else:
                logger.info("🔍 Tomato не найден или кулдаун активен")
                
            time.sleep(30)  # Проверяем каждые 30 секунд
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            time.sleep(60)

# Запускаем приложение
if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК СИСТЕМЫ С КУЛДАУНОМ")
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=discord_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # Отправляем уведомление о запуске
    send_telegram("🔍 Бот перезапущен! Мониторинг Tomato с кулдауном 4 минуты...")
    
    app.run(host='0.0.0.0', port=5000)
