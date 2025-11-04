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

def send_control_buttons(chat_id):
    """Отправляет кнопки управления"""
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ ВКЛЮЧИТЬ канал", "callback_data": "enable_channel"},
                {"text": "⏸️ ВЫКЛЮЧИТЬ канал", "callback_data": "disable_channel"}
            ],
            [
                {"text": "🔄 СТАТУС", "callback_data": "status"},
                {"text": "🔍 ПРОВЕРИТЬ СЕЙЧАС", "callback_data": "check_now"}
            ]
        ]
    }
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": "🎛️ <b>Панель управления ботом</b>\nВыберите действие:",
            "parse_mode": "HTML",
            "reply_markup": keyboard
        }
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"❌ Ошибка отправки кнопок: {e}")
        return False

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
        send_control_buttons(TELEGRAM_BOT_CHAT_ID)
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

def handle_telegram_command(update):
    """Обрабатывает команды из Telegram"""
    try:
        if 'message' in update:
            message = update['message']
            chat_id = message['chat']['id']
            text = message.get('text', '')
            
            if text == '/start':
                welcome_msg = (
                    "🎛️ <b>Панель управления мониторингом</b>\n\n"
                    "🤖 <b>Бот отслеживает:</b>\n"
                    "• Все сообщения Ember в Discord\n"
                    "• Наличие томатов в стоках\n\n"
                    "📢 <b>Канал:</b> Уведомления о томатах\n"
                    "🤖 <b>Этот бот:</b> Все сообщения + управление\n\n"
                    "Используйте кнопки ниже для управления:"
                )
                send_telegram_message(chat_id, welcome_msg)
                send_control_buttons(chat_id)
                
            elif text == '/control':
                send_control_buttons(chat_id)
                
            elif text == '/status':
                send_status(chat_id)
                
        elif 'callback_query' in update:
            callback = update['callback_query']
            chat_id = callback['message']['chat']['id']
            data = callback['data']
            
            if data == 'enable_channel':
                global channel_enabled
                channel_enabled = True
                send_telegram_message(chat_id, "✅ <b>Канал ВКЛЮЧЕН</b>\nУведомления о томатах будут приходить в канал")
                send_control_buttons(chat_id)
                
            elif data == 'disable_channel':
                channel_enabled = False
                send_telegram_message(chat_id, "⏸️ <b>Канал ВЫКЛЮЧЕН</b>\nУведомления о томатах НЕ будут приходить в канал")
                send_control_buttons(chat_id)
                
            elif data == 'status':
                send_status(chat_id)
                
            elif data == 'check_now':
                send_telegram_message(chat_id, "🔍 <b>Проверяю сообщения...</b>")
                messages = get_discord_messages()
                if messages:
                    found = check_ember_messages(messages)
                    status = "🎯 Томат найден!" if found else "🔍 Томатов нет"
                    send_telegram_message(chat_id, f"✅ <b>Проверка завершена</b>\n{status}")
                
    except Exception as e:
        logger.error(f"❌ Ошибка обработки команды: {e}")

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
                .channel {{ background: #e3f2fd; padding: 15px; margin: 10px 0; border-radius: 8px; }}
                .bot {{ background: #f3e5f5; padding: 15px; margin: 10px 0; border-radius: 8px; }}
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
            
            <p><a href="/control">Панель управления</a> | <a href="/status">Статус</a></p>
        </body>
    </html>
    """

@app.route('/control')
def control_panel():
    """Веб-панель управления"""
    return f"""
    <html>
        <head><title>Панель управления</title></head>
        <body>
            <h1>🎛️ Панель управления</h1>
            <p>Канал: <strong>{'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</strong></p>
            <button onclick="fetch('/enable_channel')">✅ Включить канал</button>
            <button onclick="fetch('/disable_channel')">⏸️ Выключить канал</button>
            <p><a href="/">На главную</a></p>
        </body>
    </html>
    """

@app.route('/enable_channel')
def enable_channel():
    global channel_enabled
    channel_enabled = True
    return "✅ Канал включен"

@app.route('/disable_channel')
def disable_channel():
    global channel_enabled
    channel_enabled = False
    return "⏸️ Канал выключен"

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    """Webhook для Telegram команд"""
    try:
        update = request.get_json()
        handle_telegram_command(update)
        return 'OK'
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}")
        return 'ERROR'

# Запускаем мониторинг
threading.Thread(target=monitor_discord, daemon=True).start()
threading.Thread(target=health_check, daemon=True).start()

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК БОТА С ПАНЕЛЬЮ УПРАВЛЕНИЯ!")
    logger.info("📢 Канал: Уведомления о томатах")
    logger.info("🤖 Бот: Все сообщения + управление")
    logger.info("🎛️ Кнопки: Включить/выключить канал")
    
    # Отправляем сообщения о запуске
    startup_msg_channel = "🚀 <b>Мониторинг запущен!</b>\n📢 Канал активен и готов к работе"
    startup_msg_bot = (
        "🚀 <b>Бот запущен с панелью управления!</b>\n\n"
        "🎛️ <b>Доступные команды:</b>\n"
        "/start - Панель управления\n"
        "/control - Кнопки управления\n" 
        "/status - Статус бота\n\n"
        "📢 <b>Канал можно включать/выключать</b> через кнопки"
    )
    
    send_to_channel(startup_msg_channel)
    send_to_bot(startup_msg_bot)
    send_control_buttons(TELEGRAM_BOT_CHAT_ID)
    
    app.run(host='0.0.0.0', port=5000)
