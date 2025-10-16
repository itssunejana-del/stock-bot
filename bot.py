from flask import Flask
import requests
import os
import time
import logging
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

# Храним ID последнего обработанного сообщения с Tomato
last_processed_message_id = None

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
    global last_processed_message_id
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=5"  # Только 5 последних
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            
            # Ищем самое новое сообщение с Tomato
            for message in messages:
                message_id = message['id']
                author = message['author']['username']
                content = message.get('content', '')
                embeds = message.get('embeds', [])
                
                # Пропускаем если это сообщение уже обрабатывали
                if message_id == last_processed_message_id:
                    continue
                
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
                        
                        # Формируем сообщение для Telegram
                        telegram_message = f"🚨 TOMATO В ПРОДАЖЕ! 🍅\n\n"
                        
                        # Добавляем информацию из эмбада
                        for field in embed.get('fields', []):
                            field_name = field.get('name', '')
                            field_value = field.get('value', '')
                            if field_name and field_value:
                                telegram_message += f"• {field_name}: {field_value}\\n"
                        
                        # Обновляем последнее обработанное сообщение
                        last_processed_message_id = message_id
                        
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
    <p>Последнее обработанное сообщение: <b id="lastMsg">Загрузка...</b></p>
    <p><a href="/check">🔍 Проверить сообщения</a></p>
    <p><a href="/reset">🔄 Сбросить историю</a></p>
    <script>
        fetch('/last_message').then(r => r.text()).then(msg => {
            document.getElementById('lastMsg').textContent = msg || 'Нет сообщений';
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
def reset_history():
    """Сбрасывает историю обработанных сообщений"""
    global last_processed_message_id
    last_processed_message_id = None
    return """
    <h1>🔄 История сброшена!</h1>
    <p>Бот будет обрабатывать все сообщения заново.</p>
    <p><a href="/">← Назад</a></p>
    """

@app.route('/last_message')
def get_last_message():
    """Возвращает ID последнего обработанного сообщения"""
    global last_processed_message_id
    return last_processed_message_id or "Нет обработанных сообщений"

def discord_monitor():
    """Основной мониторинг"""
    logger.info("🔄 ЗАПУСК ИСПРАВЛЕННОГО МОНИТОРИНГА")
    
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
                logger.info("🔍 Tomato не найден в новых сообщениях")
                
            time.sleep(30)  # Проверяем каждые 30 секунд
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            time.sleep(60)

# Запускаем приложение
if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК ИСПРАВЛЕННОЙ СИСТЕМЫ")
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=discord_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # Отправляем уведомление о запуске
    send_telegram("🔍 Бот перезапущен! Мониторинг Tomato...")
    
    app.run(host='0.0.0.0', port=5000)
