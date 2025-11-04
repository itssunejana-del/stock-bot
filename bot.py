from flask import Flask, request
import requests
import os
import time
import logging
import threading
from datetime import datetime
import re

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
processed_messages_cache = set()
telegram_offset = 0

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
    if channel_enabled and text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    else:
        logger.info("⏸️ Канал отключен или пустой текст, сообщение не отправлено")
        return False

def send_to_bot(text):
    """Отправляет сообщение в ТЕЛЕГРАМ БОТА (личные сообщения)"""
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

def send_help_message(chat_id):
    """Отправляет сообщение со списком команд"""
    help_text = (
        "🤖 <b>Бот мониторинга Grow a Garden</b>\n\n"
        "📋 <b>Доступные команды:</b>\n"
        "/start - Начать работу\n"
        "/status - Статус бота\n" 
        "/enable - Включить уведомления в канал\n"
        "/disable - Выключить уведомления в канал\n"
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
            "📱 <b>Вам в личные сообщения:</b> Все стоки от Ember\n"
            "📢 <b>В канал:</b> Только время стока с томатом\n\n"
            "Используйте /help для списка команд."
        )
        send_telegram_message(chat_id, welcome_text)
        
    elif command == '/help':
        send_help_message(chat_id)
        
    elif command == '/status':
        send_bot_status(chat_id)
        
    elif command == '/enable':
        channel_enabled = True
        send_telegram_message(chat_id, "✅ <b>Уведомления в канал ВКЛЮЧЕНЫ</b>\nТеперь томаты будут приходить в канал.")
        
    elif command == '/disable':
        channel_enabled = False
        send_telegram_message(chat_id, "⏸️ <b>Уведомления в канал ВЫКЛЮЧЕНЫ</b>\nУведомления о томатах временно приостановлены.")
        
    else:
        send_telegram_message(chat_id, "❌ Неизвестная команда. Используйте /help для списка команд.")

def telegram_poller_safe():
    """Безопасный опросщик Telegram с защитой от конфликтов"""
    global telegram_offset
    
    logger.info("🔍 Запускаю безопасный Telegram поллер...")
    
    while True:
        try:
            # Сначала удаляем вебхук на всякий случай
            try:
                delete_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
                requests.get(delete_url, timeout=5)
            except:
                pass
            
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {
                'offset': telegram_offset + 1,
                'timeout': 30,
                'limit': 1
            }
            
            logger.info(f"🔄 Проверяю обновления (offset: {telegram_offset})")
            response = requests.get(url, params=params, timeout=35)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('ok') and data.get('result'):
                    updates = data['result']
                    
                    for update in updates:
                        telegram_offset = update['update_id']
                        
                        if 'message' in update:
                            message = update['message']
                            chat_id = message['chat']['id']
                            text = message.get('text', '')
                            
                            logger.info(f"💬 Получена команда: '{text}' от {chat_id}")
                            
                            if text.startswith('/'):
                                handle_telegram_command(chat_id, text)
                else:
                    time.sleep(2)
            else:
                if response.status_code == 409:
                    logger.warning("⚠️ Конфликт с другим экземпляром. Жду 30 секунд...")
                    time.sleep(30)
                else:
                    logger.error(f"❌ Ошибка Telegram API: {response.status_code}")
                    time.sleep(10)
            
        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            logger.error(f"💥 Ошибка в телеграм поллере: {e}")
            time.sleep(10)

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

def clean_ember_text(text):
    """Очищает текст от эмодзи Discord и форматирует в красивый список"""
    # Удаляем эмодзи Discord формата <:name:123456>
    text = re.sub(r'<:[a-zA-Z0-9_]+:\d+>', '', text)
    
    # Удаляем лишние звездочки для жирного текста
    text = re.sub(r'\*\*', '', text)
    
    # Разделяем на строки и очищаем каждую
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if line and not line.startswith('Grow a Garden Stock') and not line.startswith('Seeds') and not line.startswith('Gear'):
            # Оставляем только название и количество
            if 'x' in line and any(char.isdigit() for char in line):
                cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

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
    
    # Очищаем текст
    cleaned_text = clean_ember_text(full_text)
    
    return cleaned_text.strip()

def check_ember_messages(messages):
    """Проверяет сообщения от Ember бота"""
    global last_processed_id, bot_status, last_error, processed_messages_cache
    
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
        
        # Очищаем кэш если он слишком большой
        if len(processed_messages_cache) > 100:
            processed_messages_cache = set()
            logger.info("🧹 Очистил кэш обработанных сообщений")
        
        for message in messages:
            message_id = message['id']
            
            # Если дошли до уже обработанных - выходим
            if message_id <= last_processed_id:
                break
            
            # Защита от дублирования - проверяем в кэше
            if message_id in processed_messages_cache:
                logger.info(f"⏩ Пропускаем уже обработанное сообщение: {message_id}")
                continue
            
            author = message.get('author', {}).get('username', '')
            
            # Проверяем только сообщения от Ember бота
            if 'Ember' in author:
                logger.info(f"🔍 Новое сообщение от Ember: {message_id}")
                
                # Добавляем в кэш обработанных
                processed_messages_cache.add(message_id)
                
                # 🔍 ДЕБАГ: Логируем полный текст для анализа
                content = message.get('content', '')
                embeds = message.get('embeds', [])
                logger.info(f"📄 Полный текст сообщения: {content}")
                if embeds:
                    for i, embed in enumerate(embeds):
                        logger.info(f"📊 Embed {i}: title='{embed.get('title')}', description='{embed.get('description')}'")
                
                formatted_message = format_ember_message(message)
                
                if formatted_message:
                    # 📱 ВСЕГДА отправляем ВСЕ сообщения Ember в БОТА (личные сообщения)
                    bot_message = (
                        f"🛒 <b>Новый сток от Ember</b>\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
                        f"{formatted_message}"
                    )
                    send_to_bot(bot_message)
                    
                    # 🔍 Проверяем на наличие томата (для канала)
                    full_text = content.lower() + " " + formatted_message.lower()
                    logger.info(f"🔎 Проверяю текст на томаты: {full_text[:200]}...")
                    
                    if any(tomato in full_text for tomato in ['tomato', 'томат']):
                        logger.info("🎯 ОБНАРУЖЕН ТОМАТ В СООБЩЕНИИ EMBER!")
                        
                        # 📢 В КАНАЛ - ТОЛЬКО ВРЕМЯ СТОКА С ТОМАТОМ
                        current_time = datetime.now().strftime('%H:%M:%S')
                        channel_message = f"🍅 Томат в стоке! {current_time}"
                        
                        if send_to_channel(channel_message):
                            logger.info("✅ Время стока с томатом отправлено в канал!")
                        found_tomato = True
                    else:
                        logger.info("❌ Томат не найден в сообщении")
        
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
                    logger.info("✅ Время стока с томатом отправлено в канал!")
                
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
            # Отправляем статус каждые 12 часов ТОЛЬКО В БОТА
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
            logger.info("📊 Авто-статус отправлен в бота")
            
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
                <h3>🤖 Логика работы</h3>
                <p>📱 <strong>Вам в бота:</strong> Все стоки от Ember</p>
                <p>📢 <strong>В канал:</strong> Только время стока с томатом</p>
                <p>🚫 <strong>НЕТ уведомлений в канале</strong> о запуске/ошибках</p>
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
            <p>Уведомления о томатах (время стока) снова будут приходить в канал.</p>
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
            <p>Уведомления о томатах (время стока) временно приостановлены.</p>
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
    """Резервный вебхук"""
    try:
        update = request.get_json()
        logger.info(f"📨 Получен вебхук: {update}")
        return 'OK'
    except Exception as e:
        logger.error(f"❌ Ошибка обработки вебхука: {e}")
        return 'ERROR'

def start_background_threads():
    logger.info("🔄 Запускаю фоновые потоки...")
    
    threads = [
        threading.Thread(target=monitor_discord, daemon=True),
        threading.Thread(target=telegram_poller_safe, daemon=True),
        threading.Thread(target=health_monitor, daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Поток {thread.name} запущен")
    
    return threads

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК БОТА С ДЕБАГ-ЛОГАМИ!")
    logger.info("📱 Вам в бота: ВСЕ стоки от Ember")
    logger.info("📢 В канал: ТОЛЬКО время стока с томатом")
    logger.info("🔍 ДЕБАГ: Логирую полный текст сообщений")
    
    # Запускаем фоновые потоки
    start_background_threads()
    
    # 📱 ТОЛЬКО В БОТА - никаких сообщений в канал при запуске!
    startup_msg_bot = (
        "🚀 <b>Бот запущен с дебаг-логами!</b>\n\n"
        "📱 <b>Вам в бота:</b> Все стоки от Ember\n"
        "📢 <b>В канал:</b> Только время стока с томатом\n"
        "🔍 <b>Дебаг:</b> Логирую полный текст для анализа\n\n"
        "🎛️ <b>Команды:</b>\n"
        "/start - Информация\n"
        "/status - Статус\n" 
        "/enable - Включить канал\n"
        "/disable - Выключить канал\n"
        "/help - Помощь"
    )
    
    send_to_bot(startup_msg_bot)
    
    app.run(host='0.0.0.0', port=5000)
