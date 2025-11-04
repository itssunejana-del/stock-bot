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

# Токены и ID
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

# Глобальные переменные
last_processed_id = None
startup_time = datetime.now()
channel_enabled = True  # Флаг включения/выключения канала
command_queue = []  # Очередь команд от пользователя

def send_telegram_message(chat_id, text, parse_mode="HTML"):
    """Отправляет сообщение в указанный чат/канал"""
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены переменные Telegram")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id, 
            "text": text,
            "parse_mode": parse_mode
        }
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено в Telegram ({chat_id}): {text[:100]}...")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def send_to_channel(text):
    """Отправляет сообщение в ТЕЛЕГРАМ КАНАЛ (только если включен)"""
    if channel_enabled:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    else:
        logger.info("⏸️ Канал отключен, сообщение не отправлено")
        return False

def send_to_bot(text):
    """Отправляет сообщение в ТЕЛЕГРАМ БОТА"""
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

def process_commands():
    """Обрабатывает команды из очереди"""
    global channel_enabled
    
    while True:
        try:
            if command_queue:
                command = command_queue.pop(0)
                chat_id = command['chat_id']
                text = command['text']
                
                if text == '/start' or text == '/help':
                    welcome_msg = (
                        "🎛️ <b>Панель управления мониторингом</b>\n\n"
                        "🤖 <b>Доступные команды:</b>\n"
                        "/enable - ✅ ВКЛЮЧИТЬ канал\n"
                        "/disable - ⏸️ ВЫКЛЮЧИТЬ канал\n"
                        "/status - 📊 Статус бота\n"
                        "/check - 🔍 Проверить сейчас\n"
                        "/help - ℹ️ Помощь\n\n"
                        f"📢 Канал: <b>{'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</b>"
                    )
                    send_telegram_message(chat_id, welcome_msg)
                    
                elif text == '/enable':
                    channel_enabled = True
                    send_telegram_message(chat_id, "✅ <b>Канал ВКЛЮЧЕН</b>\nУведомления о томатах будут приходить в канал")
                    
                elif text == '/disable':
                    channel_enabled = False
                    send_telegram_message(chat_id, "⏸️ <b>Канал ВЫКЛЮЧЕН</b>\nУведомления о томатах НЕ будут приходить в канал")
                    
                elif text == '/status':
                    send_status(chat_id)
                    
                elif text == '/check':
                    send_telegram_message(chat_id, "🔍 <b>Проверяю сообщения...</b>")
                    # Принудительная проверка будет выполнена в основном цикле
                    
                else:
                    send_telegram_message(chat_id, "❌ Неизвестная команда. Используйте /help для списка команд")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки команды: {e}")
        
        time.sleep(1)

def get_discord_messages():
    """Получает сообщения из Discord канала"""
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=10"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            error_msg = f"🚨 <b>Ошибка Discord</b>\nКод: {response.status_code}"
            send_to_bot(error_msg)
            return None
                
    except Exception as e:
        logger.error(f"💥 Ошибка при запросе к Discord: {e}")
        send_to_bot(f"🚨 <b>Критическая ошибка</b>\nНе удалось подключиться к Discord:\n<code>{e}</code>")
        return None

def format_ember_message(message):
    """Форматирует сообщение от Ember для Telegram"""
    content = message.get('content', '')
    embeds = message.get('embeds', [])
    
    # Собираем весь текст
    full_text = content
    for embed in embeds:
        if embed.get('title'):
            full_text += f"\n\n{embed.get('title')}"
        if embed.get('description'):
            full_text += f"\n{embed.get('description')}"
        
        for field in embed.get('fields', []):
            full_text += f"\n{field.get('name')}: {field.get('value')}"
    
    # Экранируем специальные символы для Telegram
    full_text = full_text.replace('<', '&lt;').replace('>', '&gt;')
    
    return full_text.strip()

def check_ember_messages(messages):
    """Проверяет сообщения от Ember бота"""
    global last_processed_id
    
    if not messages:
        return False
    
    # Сортируем сообщения от новых к старым
    messages.sort(key=lambda x: x['id'], reverse=True)
    
    found_tomato = False
    newest_id = messages[0]['id']
    
    # Если это первый запуск, запоминаем последнее сообщение
    if last_processed_id is None:
        last_processed_id = newest_id
        logger.info(f"🚀 Первый запуск. Запомнил сообщение: {last_processed_id}")
        send_to_bot("🚀 <b>Бот запущен и начал мониторинг!</b>")
        return False
    
    # Проверяем только сообщения новее последнего обработанного
    for message in messages:
        message_id = message['id']
        
        # Если дошли до уже обработанных - выходим
        if message_id <= last_processed_id:
            break
        
        author = message.get('author', {}).get('username', '')
        
        # Проверяем только сообщения от Ember бота
        if 'Ember' in author:
            logger.info(f"🔍 Новое сообщение от Ember: {message_id}")
            
            # Форматируем сообщение для Telegram
            formatted_message = format_ember_message(message)
            
            # Отправляем ВСЕ сообщения Ember в бота
            bot_message = (
                f"🤖 <b>Новое сообщение от Ember</b>\n"
                f"📅 ID: <code>{message_id}</code>\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
                f"📄 Содержание:\n<code>{formatted_message}</code>"
            )
            send_to_bot(bot_message)
            
            # Проверяем на наличие томата (для канала)
            full_text = formatted_message.lower()
            if any(tomato in full_text for tomato in ['tomato', ':tomato']):
                logger.info("🎯 ОБНАРУЖЕН ТОМАТ В СООБЩЕНИИ EMBER!")
                
                # Отправляем в КАНАЛ
                channel_message = (
                    f"🍅 <b>Томат в стоке!</b>\n"
                    f"📅 Время: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"🤖 От: Ember Bot\n"
                    f"🆔 ID: {message_id}"
                )
                send_to_channel(channel_message)
                found_tomato = True
    
    # Обновляем последнее обработанное сообщение
    last_processed_id = newest_id
    
    return found_tomato

def send_status(chat_id):
    """Отправляет статус бота"""
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    status_text = (
        f"📊 <b>Статус бота</b>\n"
        f"⏰ Работает: {hours:.1f} часов\n"
        f"📅 Запущен: {startup_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"🔄 Мониторю: Ember bot\n"
        f"📝 Последнее сообщение: {last_processed_id or 'Еще не проверял'}\n"
        f"✅ Все системы в норме"
    )
    
    send_telegram_message(chat_id, status_text)

def monitor_discord():
    """Основная функция мониторинга"""
    logger.info("🔄 Запуск мониторинга Discord...")
    
    error_count = 0
    max_errors = 5
    
    while True:
        try:
            messages = get_discord_messages()
            
            if messages is not None:
                found_tomato = check_ember_messages(messages)
                
                if found_tomato:
                    logger.info("✅ Уведомление о томате отправлено в канал!")
                
                error_count = 0  # Сброс счетчика ошибок
            else:
                error_count += 1
                logger.warning(f"⚠️ Ошибка получения сообщений ({error_count}/{max_errors})")
                
                if error_count >= max_errors:
                    logger.error("🚨 Слишком много ошибок, перезапуск через 5 минут...")
                    send_to_bot("🚨 <b>ВНИМАНИЕ!</b>\nБот обнаружил проблемы с подключением к Discord.\nПерезапускаюсь через 5 минут...")
                    time.sleep(300)
                    error_count = 0
            
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в мониторинге: {e}")
            send_to_bot(f"🚨 <b>Критическая ошибка!</b>\nВ мониторинге:\n<code>{e}</code>")
            error_count += 1
            time.sleep(60)

def health_check():
    """Проверка здоровья бота"""
    while True:
        try:
            uptime = datetime.now() - startup_time
            hours = uptime.total_seconds() / 3600
            
            if hours % 6 < 0.1:  # Каждые 6 часов
                status_text = (
                    f"📊 <b>Авто-статус</b>\n"
                    f"⏰ Работает: {hours:.1f} часов\n"
                    f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
                    f"🔄 Все системы в норме"
                )
                send_to_bot(status_text)
                logger.info("📊 Авто-статус отправлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки отчета: {e}")
        
        time.sleep(3600)  # Проверяем каждый час

def check_telegram_commands():
    """Проверяет новые сообщения от пользователя"""
    last_update_id = 0
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {
                'offset': last_update_id + 1,
                'timeout': 30
            }
            
            response = requests.get(url, params=params, timeout=35)
            
            if response.status_code == 200:
                data = response.json()
                if data['ok'] and data['result']:
                    for update in data['result']:
                        last_update_id = update['update_id']
                        
                        if 'message' in update:
                            message = update['message']
                            chat_id = message['chat']['id']
                            text = message.get('text', '')
                            
                            # Добавляем команду в очередь
                            command_queue.append({
                                'chat_id': chat_id,
                                'text': text
                            })
                            logger.info(f"📨 Получена команда: {text} от {chat_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки команд: {e}")
            time.sleep(10)
        
        time.sleep(1)

@app.route('/')
def home():
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    return f"""
    <html>
        <head>
            <title>🍅 Tomato Monitor</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .status {{ background: #f0f8f0; padding: 20px; border-radius: 10px; }}
                .info {{ margin: 10px 0; }}
                .commands {{ background: #e3f2fd; padding: 20px; margin: 10px 0; border-radius: 8px; }}
            </style>
        </head>
        <body>
            <h1>🍅 Умный мониторинг томатов</h1>
            
            <div class="status">
                <div class="info"><strong>Бот:</strong> Активен ✅</div>
                <div class="info"><strong>Время работы:</strong> {hours:.1f} часов</div>
                <div class="info"><strong>Запущен:</strong> {startup_time.strftime('%d.%m.%Y %H:%M:%S')}</div>
                <div class="info"><strong>Канал:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</div>
                <div class="info"><strong>Последнее сообщение:</strong> {last_processed_id or 'Еще не проверял'}</div>
            </div>
            
            <div class="commands">
                <h3>🤖 Команды для Telegram бота:</h3>
                <p><code>/start</code> - Панель управления</p>
                <p><code>/enable</code> - ✅ Включить канал</p>
                <p><code>/disable</code> - ⏸️ Выключить канал</p>
                <p><code>/status</code> - 📊 Статус бота</p>
                <p><code>/check</code> - 🔍 Проверить сейчас</p>
            </div>
            
            <p><a href="/enable_channel">✅ Включить канал</a> | <a href="/disable_channel">⏸️ Выключить канал</a></p>
        </body>
    </html>
    """

@app.route('/enable_channel')
def enable_channel():
    global channel_enabled
    channel_enabled = True
    return "✅ Канал включен. Сообщения снова будут приходить в канал."

@app.route('/disable_channel')
def disable_channel():
    global channel_enabled
    channel_enabled = False
    return "⏸️ Канал выключен. Сообщения НЕ будут приходить в канал."

# Запускаем все потоки
threading.Thread(target=monitor_discord, daemon=True).start()
threading.Thread(target=health_check, daemon=True).start()
threading.Thread(target=check_telegram_commands, daemon=True).start()
threading.Thread(target=process_commands, daemon=True).start()

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК БОТА С ТЕКСТОВЫМИ КОМАНДАМИ!")
    logger.info("📢 Канал: Уведомления о томатах")
    logger.info("🤖 Бот: Все сообщения + управление")
    logger.info("⌨️ Команды: /start, /enable, /disable, /status, /check")
    
    # Отправляем сообщения о запуске
    startup_msg_channel = "🚀 <b>Мониторинг запущен!</b>\n📢 Канал активен и готов к работе"
    startup_msg_bot = (
        "🚀 <b>Бот запущен с текстовыми командами!</b>\n\n"
        "🎛️ <b>Доступные команды:</b>\n"
        "/start - Панель управления\n"
        "/enable - ✅ Включить канал\n"
        "/disable - ⏸️ Выключить канал\n"
        "/status - 📊 Статус бота\n"
        "/check - 🔍 Проверить сейчас\n\n"
        f"📢 Канал: <b>{'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</b>"
    )
    
    send_to_channel(startup_msg_channel)
    send_to_bot(startup_msg_bot)
    
    app.run(host='0.0.0.0', port=5000)
