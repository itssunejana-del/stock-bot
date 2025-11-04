from flask import Flask, request
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
channel_enabled = True
bot_status = "🟢 Работает нормально"
last_error = None

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

def send_help_message(chat_id):
    """Отправляет сообщение со списком команд"""
    help_text = (
        "🤖 <b>Бот мониторинга Grow a Garden</b>\n\n"
        "📋 <b>Доступные команды:</b>\n"
        "/start - Начать работу\n"
        "/status - Статус бота\n" 
        "/enable - Включить уведомления\n"
        "/disable - Выключить уведомления\n"
        "/help - Показать это сообщение\n\n"
        "🔄 Бот автоматически отслеживает стоки от Ember и присылает уведомления о томатах."
    )
    send_telegram_message(chat_id, help_text)

def send_bot_status(chat_id):
    """Отправляет статус бота"""
    global bot_status, last_error, channel_enabled
    
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    status_text = (
        f"📊 <b>Статус бота</b>\n\n"
        f"{bot_status}\n"
        f"⏰ Время работы: {hours:.1f} часов\n"
        f"📅 Запущен: {startup_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"🔄 Отслеживаю: Ember bot\n"
        f"📝 Последнее сообщение: {last_processed_id or 'Еще не проверял'}\n"
    )
    
    if last_error:
        status_text += f"\n⚠️ <b>Последняя ошибка:</b>\n<code>{last_error}</code>"
    
    send_telegram_message(chat_id, status_text)

def handle_telegram_command(chat_id, command):
    """Обрабатывает команды Telegram"""
    global channel_enabled
    
    logger.info(f"🎯 Обрабатываю команду: {command} от {chat_id}")
    
    if command == '/start':
        welcome_text = (
            "🎮 <b>Добро пожаловать!</b>\n\n"
            "Я бот для отслеживания стоков в игре <b>Grow a Garden</b>.\n"
            "Автоматически мониторю Discord канал с ботом Ember и присылаю уведомления о стоках.\n\n"
            "Используйте /help для списка команд."
        )
        send_telegram_message(chat_id, welcome_text)
        
    elif command == '/help':
        send_help_message(chat_id)
        
    elif command == '/status':
        send_bot_status(chat_id)
        
    elif command == '/enable':
        channel_enabled = True
        send_telegram_message(chat_id, "✅ <b>Уведомления ВКЛЮЧЕНЫ</b>\nТеперь вы будете получать уведомления о томатах в канале.")
        
    elif command == '/disable':
        channel_enabled = False
        send_telegram_message(chat_id, "⏸️ <b>Уведомления ВЫКЛЮЧЕНЫ</b>\nУведомления о томатах временно приостановлены.")
        
    else:
        send_telegram_message(chat_id, "❌ Неизвестная команда. Используйте /help для списка команд.")

def telegram_poller():
    """Опрашивает Telegram API на наличие новых команд"""
    logger.info("🔍 Запускаю Telegram поллер для обработки команд...")
    last_update_id = 0
    
    while True:
        try:
            logger.info(f"🔄 Проверяю обновления Telegram (offset: {last_update_id})")
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {
                'offset': last_update_id + 1,
                'timeout': 10
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"📨 Получен ответ от Telegram: {data}")
                
                if data.get('ok') and data.get('result'):
                    updates = data['result']
                    logger.info(f"📥 Найдено обновлений: {len(updates)}")
                    
                    for update in updates:
                        last_update_id = update['update_id']
                        logger.info(f"🔍 Обрабатываю update_id: {last_update_id}")
                        
                        if 'message' in update:
                            message = update['message']
                            chat_id = message['chat']['id']
                            text = message.get('text', '')
                            
                            logger.info(f"💬 Получено сообщение: '{text}' от {chat_id}")
                            
                            if text.startswith('/'):
                                handle_telegram_command(chat_id, text)
                else:
                    logger.info("📭 Нет новых обновлений")
            else:
                logger.error(f"❌ Ошибка Telegram API: {response.status_code} - {response.text}")
            
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в телеграм поллере: {e}")
            time.sleep(10)

def setup_webhook():
    """Удаляет вебхук если он установлен, чтобы использовать Long Polling"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            logger.info("✅ Вебхук удален, использую Long Polling")
        else:
            logger.warning(f"⚠️ Не удалось удалить вебхук: {response.text}")
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении вебхука: {e}")

def get_discord_messages():
    """Получает сообщения из Discord канала"""
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=10"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            return response.json()
        else:
            error_msg = f"Ошибка Discord API: {response.status_code}"
            logger.error(f"❌ {error_msg}")
            return None
                
    except Exception as e:
        error_msg = f"Ошибка подключения к Discord: {e}"
        logger.error(f"💥 {error_msg}")
        return None

def format_ember_message(message):
    """Форматирует сообщение от Ember для Telegram"""
    content = message.get('content', '')
    embeds = message.get('embeds', [])
    
    full_text = content
    for embed in embeds:
        if embed.get('title'):
            full_text += f"\n\n{embed.get('title')}"
        if embed.get('description'):
            full_text += f"\n{embed.get('description')}"
        
        for field in embed.get('fields', []):
            full_text += f"\n{field.get('name')}: {field.get('value')}"
    
    full_text = full_text.replace('<', '&lt;').replace('>', '&gt;')
    return full_text.strip()

def check_ember_messages(messages):
    """Проверяет сообщения от Ember бота"""
    global last_processed_id, bot_status, last_error
    
    if not messages:
        return False
    
    try:
        messages.sort(key=lambda x: x['id'], reverse=True)
        
        found_tomato = False
        newest_id = messages[0]['id']
        
        if last_processed_id is None:
            last_processed_id = newest_id
            logger.info(f"🚀 Первый запуск. Запомнил сообщение: {last_processed_id}")
            send_to_bot("🚀 <b>Бот запущен и начал мониторинг!</b>")
            return False
        
        for message in messages:
            message_id = message['id']
            
            if message_id <= last_processed_id:
                break
            
            author = message.get('author', {}).get('username', '')
            
            if 'Ember' in author:
                logger.info(f"🔍 Новое сообщение от Ember: {message_id}")
                
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
                    
                    channel_message = (
                        f"🍅 <b>Томат в стоке!</b>\n"
                        f"📅 Время: {datetime.now().strftime('%H:%M:%S')}\n"
                        f"🤖 От: Ember Bot\n"
                        f"🆔 ID: {message_id}"
                    )
                    send_to_channel(channel_message)
                    found_tomato = True
        
        last_processed_id = newest_id
        bot_status = "🟢 Работает нормально"
        last_error = None
        return found_tomato
        
    except Exception as e:
        error_msg = f"Ошибка обработки сообщений: {e}"
        logger.error(f"💥 {error_msg}")
        bot_status = "🔴 Ошибка обработки"
        last_error = error_msg
        send_to_bot(f"🚨 <b>Ошибка в мониторинге:</b>\n<code>{error_msg}</code>")
        return False

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
                
                error_count = 0
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
            time.sleep(60)

def health_monitor():
    """Мониторинг здоровья бота"""
    logger.info("❤️ Запускаю монитор здоровья...")
    while True:
        try:
            # Отправляем статус каждые 12 часов
            time.sleep(43200)  # 12 часов
            
            uptime = datetime.now() - startup_time
            hours = uptime.total_seconds() / 3600
            
            status_report = (
                f"📊 <b>Авто-статус</b>\n"
                f"⏰ Работает: {hours:.1f} часов\n"
                f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
                f"🔄 {bot_status}\n"
                f"✅ Бот стабильно работает"
            )
            
            send_to_bot(status_report)
            logger.info("📊 Авто-статус отправлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки авто-статуса: {e}")

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
                .button {{ background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 5px; }}
                .button-disable {{ background: #f44336; }}
            </style>
        </head>
        <body>
            <h1>🍅 Умный мониторинг томатов</h1>
            
            <div class="status">
                <h3>📊 Статус системы</h3>
                <div class="info"><strong>Состояние:</strong> {bot_status}</div>
                <div class="info"><strong>Время работы:</strong> {hours:.1f} часов</div>
                <div class="info"><strong>Канал:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</div>
                <div class="info"><strong>Последнее сообщение:</strong> {last_processed_id or 'Еще не проверял'}</div>
            </div>
            
            <div class="commands">
                <h3>🎛️ Управление</h3>
                <a href="/enable_channel" class="button">✅ Включить канал</a>
                <a href="/disable_channel" class="button button-disable">⏸️ Выключить канал</a>
                <a href="/status" class="button">📊 Статус</a>
            </div>
            
            <div class="commands">
                <h3>🤖 Команды в Telegram</h3>
                <p><code>/start</code> - Начать работу</p>
                <p><code>/status</code> - Статус бота</p>
                <p><code>/enable</code> - Включить уведомления</p>
                <p><code>/disable</code> - Выключить уведомления</p>
                <p><code>/help</code> - Помощь</p>
            </div>
        </body>
    </html>
    """

@app.route('/enable_channel')
def enable_channel():
    global channel_enabled
    channel_enabled = True
    return """
    <html>
        <head><title>Канал включен</title></head>
        <body>
            <h2>✅ Канал включен</h2>
            <p>Уведомления о томатах снова будут приходить в канал.</p>
            <a href="/">← Назад к панели управления</a>
        </body>
    </html>
    """

@app.route('/disable_channel')
def disable_channel():
    global channel_enabled
    channel_enabled = False
    return """
    <html>
        <head><title>Канал выключен</title></head>
        <body>
            <h2>⏸️ Канал выключен</h2>
            <p>Уведомления о томатах временно приостановлены.</p>
            <a href="/">← Назад к панели управления</a>
        </body>
    </html>
    """

@app.route('/status')
def status_page():
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    status_html = f"""
    <html>
        <head><title>Статус бота</title></head>
        <body>
            <h2>📊 Детальный статус</h2>
            <p><strong>Состояние:</strong> {bot_status}</p>
            <p><strong>Время работы:</strong> {hours:.1f} часов</p>
            <p><strong>Запущен:</strong> {startup_time.strftime('%d.%m.%Y %H:%M:%S')}</p>
            <p><strong>Канал:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</p>
            <p><strong>Последнее сообщение:</strong> {last_processed_id or 'Еще не проверял'}</p>
            {"<p><strong>Последняя ошибка:</strong> " + last_error + "</p>" if last_error else ""}
            <a href="/">← Назад к панели управления</a>
        </body>
    </html>
    """
    return status_html

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обрабатывает вебхук от Telegram (если кто-то его настроил)"""
    try:
        update = request.get_json()
        logger.info(f"📨 Получен вебхук: {update}")
        return 'OK'
    except Exception as e:
        logger.error(f"❌ Ошибка обработки вебхука: {e}")
        return 'ERROR'

# Запускаем все потоки
def start_background_threads():
    logger.info("🔄 Запускаю фоновые потоки...")
    
    threads = [
        threading.Thread(target=monitor_discord, daemon=True),
        threading.Thread(target=telegram_poller, daemon=True),
        threading.Thread(target=health_monitor, daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Поток {thread.name} запущен")
    
    return threads

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК УЛУЧШЕННОГО БОТА!")
    logger.info("📢 Канал: Уведомления о томатах")
    logger.info("🤖 Бот: Все сообщения + управление")
    logger.info("⌨️ Команды: /start, /status, /enable, /disable")
    logger.info("📊 Авто-статус: каждые 12 часов")
    
    # Удаляем вебхук если он есть
    setup_webhook()
    
    # Запускаем фоновые потоки
    start_background_threads()
    
    # Отправляем сообщения о запуске
    startup_msg_channel = "🚀 <b>Мониторинг запущен!</b>\n📢 Канал активен и готов к работе"
    startup_msg_bot = (
        "🚀 <b>Бот запущен с новыми функциями!</b>\n\n"
        "🎛️ <b>Доступные команды:</b>\n"
        "/start - Начать работу\n"
        "/status - Статус бота\n" 
        "/enable - Включить уведомления\n"
        "/disable - Выключить уведомления\n"
        "/help - Помощь\n\n"
        "Напишите /start для начала работы"
    )
    
    send_to_channel(startup_msg_channel)
    send_to_bot(startup_msg_bot)
    
    app.run(host='0.0.0.0', port=5000)
