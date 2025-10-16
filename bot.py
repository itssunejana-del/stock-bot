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

# Храним ID последнего обработанного сообщения
last_processed_message_id = None
# Время последнего уведомления
last_notification_time = None
# Минимальный интервал между уведомлениями (5 минут)
NOTIFICATION_COOLDOWN = timedelta(minutes=5)

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
    """Проверяет самое последнее сообщение в канале Discord"""
    global last_processed_message_id, last_notification_time
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=1"  # Только 1 последнее сообщение
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            
            if not messages:
                return False, "Нет сообщений в канале", None
            
            message = messages[0]  # Самое последнее сообщение
            message_id = message['id']
            author = message['author']['username']
            content = message.get('content', '')
            embeds = message.get('embeds', [])
            
            # Пропускаем если это сообщение уже обрабатывали
            if message_id == last_processed_message_id:
                return False, "Сообщение уже обработано", message_id
            
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
                    logger.info(f"🎯 НОВЫЙ TOMATO НАЙДЕН В СООБЩЕНИИ {message_id}!")
                    
                    current_time = datetime.now()
                    
                    # Проверяем глобальный кулдаун
                    if last_notification_time and (current_time - last_notification_time) < NOTIFICATION_COOLDOWN:
                        logger.info(f"⏳ Пропускаем уведомление - глобальный кулдаун активен")
                        # Но все равно отмечаем сообщение как обработанное
                        last_processed_message_id = message_id
                        return False, "Глобальный кулдаун активен", message_id
                    
                    # Формируем сообщение для Telegram
                    telegram_message = f"🚨 TOMATO В ПРОДАЖЕ! 🍅\n\n"
                    
                    # Добавляем информацию из эмбада
                    for field in embed.get('fields', []):
                        field_name = field.get('name', '')
                        field_value = field.get('value', '')
                        if field_name and field_value:
                            telegram_message += f"• {field_name}: {field_value}\n"
                    
                    # Обновляем время последнего уведомления и ID сообщения
                    last_notification_time = current_time
                    last_processed_message_id = message_id
                    
                    logger.info(f"✅ Готово к отправке уведомления для {message_id}")
                    
                    return True, telegram_message, message_id
            
            # Если Tomato не найден, все равно отмечаем сообщение как обработанное
            last_processed_message_id = message_id
            return False, "Tomato не найден в последнем сообщении", message_id
            
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
    <p>Последнее сообщение: <b id="lastMsg">Загрузка...</b></p>
    <p>Последнее уведомление: <b id="lastNotif">Загрузка...</b></p>
    <p><a href="/check">🔍 Проверить сейчас</a></p>
    <p><a href="/reset">🔄 Сбросить кулдаун</a></p>
    <script>
        function updateStatus() {
            fetch('/last_message').then(r => r.text()).then(msg => {
                document.getElementById('lastMsg').textContent = msg || 'Нет сообщений';
            });
            fetch('/last_notification').then(r => r.text()).then(msg => {
                document.getElementById('lastNotif').textContent = msg || 'Нет уведомлений';
            });
        }
        updateStatus();
        setInterval(updateStatus, 5000);
    </script>
    """

@app.route('/check')
def check_messages():
    """Проверяет сообщения"""
    found, message, msg_id = check_discord_messages()
    
    result = "🍅 TOMATO НАЙДЕН!" if found else "❌ Tomato не найден"
    
    if found:
        success = send_telegram(message)
        result += " ✅ Уведомление отправлено!" if success else " ❌ Ошибка отправки"
    
    return f"""
    <h1>Результат проверки</h1>
    <p>Результат: <b>{result}</b></p>
    <p>ID сообщения: {msg_id or 'Нет'}</p>
    <p>Сообщение: {message}</p>
    <p><a href="/">← Назад</a></p>
    """

@app.route('/reset')
def reset_cooldown():
    """Сбрасывает кулдаун"""
    global last_notification_time
    last_notification_time = None
    return """
    <h1>🔄 Кулдаун сброшен!</h1>
    <p>Бот отправит уведомление при следующем обнаружении Tomato.</p>
    <p><a href="/">← Назад</a></p>
    """

@app.route('/last_message')
def get_last_message():
    """Возвращает ID последнего обработанного сообщения"""
    global last_processed_message_id
    return last_processed_message_id or "Нет обработанных сообщений"

@app.route('/last_notification')
def get_last_notification():
    """Возвращает время последнего уведомления"""
    global last_notification_time
    if last_notification_time:
        time_passed = datetime.now() - last_notification_time
        minutes_passed = int(time_passed.total_seconds() / 60)
        seconds_passed = int(time_passed.total_seconds() % 60)
        time_left = NOTIFICATION_COOLDOWN - time_passed
        if time_left.total_seconds() > 0:
            minutes_left = int(time_left.total_seconds() / 60)
            seconds_left = int(time_left.total_seconds() % 60)
            return f"{last_notification_time.strftime('%H:%M:%S')} ({minutes_passed}м {seconds_passed}с назад) - кулдаун: {minutes_left}м {seconds_left}с"
        else:
            return f"{last_notification_time.strftime('%H:%M:%S')} ({minutes_passed}м {seconds_passed}с назад) - готов к отправке"
    return "Нет уведомлений"

def discord_monitor():
    """Основной мониторинг"""
    logger.info("🔄 ЗАПУСК ФИНАЛЬНОГО МОНИТОРИНГА")
    
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
                logger.info("🔍 Новых сообщений с Tomato нет")
                
            time.sleep(10)  # Проверяем каждые 10 секунд для быстрого реагирования
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            time.sleep(30)

# Запускаем приложение
if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК ФИНАЛЬНОЙ СИСТЕМЫ")
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=discord_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # Отправляем уведомление о запуске
    send_telegram("🔍 Бот запущен! Мониторинг Tomato каждые 10 секунд...")
    
    app.run(host='0.0.0.0', port=5000)
