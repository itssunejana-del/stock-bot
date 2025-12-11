from flask import Flask, request, jsonify
import requests
import os
import time
import logging
import threading
from datetime import datetime
import re
import json
import queue

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
WEBHOOK_SEEDS_URL = os.getenv('WEBHOOK_SEEDS')
WEBHOOK_EGGS_URL = os.getenv('WEBHOOK_EGGS')
WEBHOOK_PASS_SHOP_URL = os.getenv('WEBHOOK_PASS_SHOP')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# ==================== ОТСЛЕЖИВАЕМЫЕ ПРЕДМЕТЫ ====================
TARGET_SEEDS = {
    'octobloom': {
        'keywords': ['octobloom', 'октоблум', ':octobloom'],
        'sticker_id': "CAACAgIAAxkBAAEP1btpIXhIEvgVEK4c6ugJv1EgP7UY-wAChokAAtZpCElVMcRUgb_jdDYE",
        'emoji': '🐙',
        'display_name': 'Octobloom'
    },
    'zebrazinkle': {
        'keywords': ['zebrazinkle', 'zebra zinkle', ':zebrazinkle'],
        'sticker_id': "CAACAgIAAxkBAAEPwjJpFDhW_6Vu29vF7DrTHFBcSf_WIAAC1XkAAkCXoUgr50G4SlzwrzYE",
        'emoji': '🦓',
        'display_name': 'Zebrazinkle'
    },
    'peppermint_vine': {
        'keywords': ['peppermint vine', 'peppermintvine', ':peppermintvine', 'перечная лоза', 'перечная'],
        'sticker_id': "CAACAgIAAxkBAAEP9hZpNtYLGgXJ5UmFIzEjQ6tL6jX-_QACrokAAk1ouUn1z9iCPYIanzYE",
        'emoji': '🌿',
        'display_name': 'Peppermint Vine'
    },
    'gem_egg': {
        'keywords': ['gem egg', 'gemegg', ':gemegg'],
        'sticker_id': "CAACAgIAAxkBAAEP1b9pIXhSl-ElpsKgOEEY-8oOmJ1qnAACI4MAAq6w2EinW-vu8EV_RzYE",
        'emoji': '💎',
        'display_name': 'Gem Egg'
    },
    'pollen_cone': {
        'keywords': ['pollen cone', 'pollencone', ':pollencone', 'пыльцевая шишка'],
        'sticker_id': "CAACAgIAAxkBAAEP-4hpOtmoKIOXpzx89yFx3StQK77KzQACQI8AAuZU2Emfi_MTLWoHDjYE",
        'emoji': '🍯',
        'display_name': 'Pollen Cone'
    },
    'tomato': {
        'keywords': ['tomato', 'томат', ':tomato'],
        'sticker_id': "CAACAgIAAxkBAAEP-3lpOtdl3thyaZN8BfxTSAvD6kEkKgACf3sAAoEeWUgkKobs-st7ojYE",
        'emoji': '🍅',
        'display_name': 'Tomato'
    }
}

# ==================== КОНФИГУРАЦИЯ КАНАЛОВ ====================
# Используем webhook_url как ключ, а channel_id будем получать из вебхука
CHANNEL_CONFIGS = {}

# Канал семян
if WEBHOOK_SEEDS_URL:
    CHANNEL_CONFIGS[WEBHOOK_SEEDS_URL] = {
        'type': 'seeds',
        'name': '🌱 Семена',
        'webhook_url': WEBHOOK_SEEDS_URL,
        'channel_id': None,  # Будем получать из вебхука
        'update_interval': 300,
        'burst_schedule': [20, 40, 60, 120, 180],
        'idle_interval': 60,
        'last_update_time': None,
        'next_check_time': None,
        'in_burst_mode': False,
        'burst_index': 0
    }
    logger.info(f"✅ Настроен канал Семена")

# Канал яиц
if WEBHOOK_EGGS_URL:
    CHANNEL_CONFIGS[WEBHOOK_EGGS_URL] = {
        'type': 'eggs',
        'name': '🥚 Яйца',
        'webhook_url': WEBHOOK_EGGS_URL,
        'channel_id': None,  # Будем получать из вебхука
        'update_interval': 1800,
        'burst_schedule': [30, 60, 120, 300, 600, 1200],
        'idle_interval': 300,
        'last_update_time': None,
        'next_check_time': None,
        'in_burst_mode': False,
        'burst_index': 0
    }
    logger.info(f"✅ Настроен канал Яйца")

# Канал пасс-шопа
if WEBHOOK_PASS_SHOP_URL:
    CHANNEL_CONFIGS[WEBHOOK_PASS_SHOP_URL] = {
        'type': 'pass_shop',
        'name': '🎫 Пасс-шоп',
        'webhook_url': WEBHOOK_PASS_SHOP_URL,
        'channel_id': None,  # Будем получать из вебхука
        'update_interval': 300,
        'burst_schedule': [40, 70, 100],
        'idle_interval': 300,
        'last_update_time': None,
        'next_check_time': None,
        'in_burst_mode': False,
        'burst_index': 0
    }
    logger.info(f"✅ Настроен канал Пасс-шоп")

if not CHANNEL_CONFIGS:
    logger.error("❌ Нет настроенных вебхуков!")
else:
    logger.info(f"📡 Настроено {len(CHANNEL_CONFIGS)} канала(ов)")

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
last_processed_ids = {}
processed_messages_cache = set()
startup_time = datetime.now()
channel_enabled = True
bot_status = "🟢 Ожидание вебхуков"
last_error = None
found_seeds_count = {name: 0 for name in TARGET_SEEDS.keys()}
ping_count = 0
last_ping_time = None
telegram_offset = 0
request_queue = queue.Queue()

# ==================== ПОМОЩНИКИ ДЛЯ КАНАЛОВ ====================
def get_channel_config_by_url(webhook_url):
    """Получает конфигурацию канала по URL вебхука"""
    return CHANNEL_CONFIGS.get(webhook_url)

def get_channel_config_by_id(channel_id):
    """Получает конфигурацию канала по ID канала"""
    for config in CHANNEL_CONFIGS.values():
        if config.get('channel_id') == channel_id:
            return config
    return None

def update_channel_id(webhook_url, channel_id):
    """Обновляет ID канала в конфигурации"""
    config = CHANNEL_CONFIGS.get(webhook_url)
    if config and not config.get('channel_id'):
        config['channel_id'] = channel_id
        logger.info(f"📝 Обновлен channel_id для {config['name']}: {channel_id}")
        return True
    return False

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML"):
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены переменные Telegram")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, data=data, timeout=15)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено в Telegram ({chat_id}): {text[:100]}...")
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram, жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Ошибка Telegram {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def send_telegram_sticker(chat_id, sticker_id):
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены переменные Telegram")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {"chat_id": chat_id, "sticker": sticker_id}
        response = requests.post(url, data=data, timeout=15)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлен стикер в Telegram ({chat_id})")
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram, жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Ошибка отправки стикера {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def send_to_channel(text=None, sticker_id=None):
    if not channel_enabled:
        logger.info("⏸️ Канал отключен")
        return False
    
    if not hasattr(send_to_channel, 'last_channel_message_time'):
        send_to_channel.last_channel_message_time = 0
    
    current_time = time.time()
    time_since_last = current_time - send_to_channel.last_channel_message_time
    
    if time_since_last < 2 and time_since_last >= 0:
        wait_time = 2 - time_since_last
        logger.info(f"⏸️ Защита от спама: жду {wait_time:.1f} сек")
        time.sleep(wait_time)
    
    send_to_channel.last_channel_message_time = time.time()
    
    if sticker_id:
        return send_telegram_sticker(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    
    return False

def send_to_bot(text):
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

# ==================== DISCORD API ====================
def fetch_discord_channel_messages(channel_id, limit=10):
    if not DISCORD_TOKEN:
        logger.error("❌ Нет токена Discord")
        return None
    
    if not channel_id or not isinstance(channel_id, (int, str)) or not str(channel_id).isdigit():
        logger.error(f"❌ Неверный channel_id: {channel_id}")
        return None
    
    try:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            messages = response.json()
            logger.info(f"📨 Получено {len(messages)} сообщений из канала {channel_id}")
            return messages
        elif response.status_code == 429:
            retry_after = response.json().get('retry_after', 1)
            logger.warning(f"⚠️ Лимит Discord API, жду {retry_after} сек")
            time.sleep(retry_after)
            return None
        else:
            logger.error(f"❌ Ошибка Discord API {response.status_code}: {response.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Discord: {e}")
        return None

# ==================== ОБРАБОТКА СООБЩЕНИЙ ====================
def clean_text_for_display(text):
    text = re.sub(r'<:[a-zA-Z0-9_]+:(\d+)>', '', text)
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'<t:\d+:[tR]>', '', text)
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if line and ('x' in line or ':' in line or any(word in line.lower() for word in ['seeds', 'gear', 'alert', 'stock', 'egg', 'pass'])):
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def extract_all_text_from_message(message):
    content = message.get('content', '')
    embeds = message.get('embeds', [])
    
    all_text = content
    for embed in embeds:
        if embed.get('title'):
            all_text += f"\n{embed.get('title')}"
        if embed.get('description'):
            all_text += f"\n{embed.get('description')}"
        for field in embed.get('fields', []):
            field_name = field.get('name', '')
            field_value = field.get('value', '')
            all_text += f"\n{field_name} {field_value}"
    
    return all_text

def format_message_for_bot(message):
    content = message.get('content', '')
    embeds = message.get('embeds', [])
    
    full_text = content
    for embed in embeds:
        if embed.get('title'):
            title = re.sub(r'<t:\d+:[tR]>', '', embed.get('title', ''))
            if title.strip():
                full_text += f"\n\n{title}"
        if embed.get('description'):
            full_text += f"\n{embed.get('description')}"
        for field in embed.get('fields', []):
            field_name = field.get('name', '')
            field_value = field.get('value', '')
            if field_name and field_value:
                full_text += f"\n\n{field_name}:\n{field_value}"
    
    cleaned_text = clean_text_for_display(full_text)
    return cleaned_text.strip()

def process_discord_message(message_data, webhook_url=None, channel_id=None):
    global found_seeds_count, bot_status, last_error
    
    try:
        message_id = message_data.get('id')
        
        if message_id in processed_messages_cache:
            logger.debug(f"⏩ Пропускаем уже обработанное сообщение: {message_id}")
            return False
        
        processed_messages_cache.add(message_id)
        
        author = message_data.get('author', {}).get('username', '')
        is_bot = message_data.get('author', {}).get('bot', False)
        
        if not is_bot and 'kiro' not in author.lower():
            logger.debug(f"⏩ Пропускаем сообщение от {author} (не Kiro)")
            return False
        
        logger.info(f"🤖 Получено сообщение от {author}: {message_id}")
        
        # Отправляем в бота
        formatted_message = format_message_for_bot(message_data)
        if formatted_message:
            current_time = datetime.now().strftime('%H:%M:%S')
            config = get_channel_config_by_url(webhook_url) if webhook_url else None
            channel_name = config['name'] if config else "Вебхук"
            
            bot_message = (
                f"📥 Новое сообщение\n"
                f"🤖 Автор: {author}\n"
                f"📡 Канал: {channel_name}\n"
                f"⏰ Время: {current_time}\n\n"
                f"<code>{formatted_message}</code>"
            )
            send_to_bot(bot_message)
        
        # Проверяем на наличие отслеживаемых предметов
        full_search_text = extract_all_text_from_message(message_data)
        search_text_lower = full_search_text.lower()
        
        found_tracked_items = []
        
        for seed_name, seed_config in TARGET_SEEDS.items():
            for keyword in seed_config['keywords']:
                if keyword in search_text_lower:
                    found_seeds_count[seed_name] += 1
                    found_tracked_items.append(seed_config['display_name'])
                    logger.info(f"🎯 ОБНАРУЖЕН {seed_name.upper()}! Ключевое слово: '{keyword}'")
                    
                    # Отправляем стикер в канал
                    sticker_sent = send_to_channel(sticker_id=seed_config['sticker_id'])
                    
                    if sticker_sent:
                        logger.info(f"✅ Стикер {seed_config['emoji']} отправлен в канал")
                        send_to_bot(f"✅ Стикер {seed_config['emoji']} отправлен в канал")
                    else:
                        logger.error(f"❌ Ошибка отправки стикера {seed_config['emoji']}")
        
        # Если нашли отслеживаемые предметы, запускаем burst режим
        if found_tracked_items and webhook_url:
            config = get_channel_config_by_url(webhook_url)
            if config and config.get('channel_id'):
                config['last_update_time'] = time.time()
                config['in_burst_mode'] = True
                config['burst_index'] = 0
                logger.info(f"🚀 Запускаю burst режим для {config['name']}")
                schedule_next_burst_request(webhook_url)
        
        bot_status = "🟢 Получено сообщение через вебхук"
        last_error = None
        return len(found_tracked_items) > 0
        
    except Exception as e:
        error_msg = f"Ошибка обработки сообщения: {e}"
        logger.error(f"💥 {error_msg}")
        bot_status = "🔴 Ошибка обработки"
        last_error = error_msg
        send_to_bot(f"🚨 <b>Ошибка обработки:</b>\n<code>{error_msg}</code>")
        return False

# ==================== РАСПИСАНИЕ ЗАПРОСОВ ====================
def schedule_next_burst_request(webhook_url):
    config = get_channel_config_by_url(webhook_url)
    if not config or not config['in_burst_mode']:
        return
    
    burst_schedule = config['burst_schedule']
    burst_index = config['burst_index']
    
    if burst_index >= len(burst_schedule):
        config['in_burst_mode'] = False
        config['burst_index'] = 0
        logger.info(f"⏹️ Завершен burst режим для {config['name']}")
        return
    
    delay = burst_schedule[burst_index]
    execute_time = time.time() + delay
    
    request_queue.put({
        'type': 'burst_request',
        'webhook_url': webhook_url,
        'execute_time': execute_time,
        'delay': delay
    })
    
    logger.info(f"📅 Запланирован burst запрос #{burst_index+1} для {config['name']} через {delay} сек")
    config['burst_index'] += 1

def execute_burst_request(webhook_url):
    config = get_channel_config_by_url(webhook_url)
    if not config or not config.get('channel_id'):
        logger.error(f"❌ Нет channel_id для {config['name'] if config else 'unknown'}")
        return
    
    logger.info(f"🔍 Выполняю burst запрос для {config['name']}")
    
    messages = fetch_discord_channel_messages(config['channel_id'])
    if messages:
        for message in messages[:5]:
            process_discord_message(message, webhook_url, config['channel_id'])
    
    schedule_next_burst_request(webhook_url)

# ==================== ВЕБХУК ОБРАБОТЧИК ====================
@app.route('/discord_webhook', methods=['POST'])
def discord_webhook():
    try:
        data = request.json
        logger.info(f"📨 Получен вебхук от Discord")
        
        # Логируем для отладки
        logger.debug(f"Вебхук данные: {json.dumps(data, indent=2)[:500]}...")
        
        # Получаем channel_id из вебхука
        channel_id = data.get('channel_id')
        webhook_id = data.get('webhook_id')
        
        # Ищем конфигурацию по webhook_id (содержится в URL)
        webhook_url = None
        for url, config in CHANNEL_CONFIGS.items():
            if str(webhook_id) in url:
                webhook_url = url
                break
        
        if not webhook_url:
            logger.warning(f"⚠️ Неизвестный вебхук: {webhook_id}")
            return jsonify({'status': 'unknown_webhook'}), 200
        
        # Обновляем channel_id если он еще не сохранен
        config = get_channel_config_by_url(webhook_url)
        if config and not config.get('channel_id') and channel_id:
            update_channel_id(webhook_url, channel_id)
        
        # Обрабатываем сообщение
        found_items = process_discord_message(data, webhook_url, channel_id)
        
        if found_items:
            logger.info("✅ Вебхук обработан, найдены отслеживаемые предметы")
        else:
            logger.info("✅ Вебхук обработан, отслеживаемых предметов нет")
        
        return jsonify({'status': 'ok'}), 200
    
    except Exception as e:
        logger.error(f"❌ Ошибка обработки вебхука: {e}")
        send_to_bot(f"🚨 <b>Ошибка вебхука:</b>\n<code>{e}</code>")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==================== РАБОТНИК ОЧЕРЕДИ ====================
def queue_worker():
    logger.info("👷 Запускаю работника очереди...")
    
    while True:
        try:
            task = request_queue.get(timeout=1)
            
            current_time = time.time()
            execute_time = task.get('execute_time', 0)
            
            if current_time < execute_time:
                time_to_wait = execute_time - current_time
                if time_to_wait > 1:
                    request_queue.put(task)
                    time.sleep(1)
                continue
            
            task_type = task.get('type')
            webhook_url = task.get('webhook_url')
            
            if task_type == 'burst_request' and webhook_url:
                execute_burst_request(webhook_url)
            
            request_queue.task_done()
            
        except queue.Empty:
            time.sleep(0.1)
        except Exception as e:
            logger.error(f"❌ Ошибка в работнике очереди: {e}")
            time.sleep(1)

# ==================== ФОЛБЭК ПРОВЕРКИ ====================
def fallback_checker():
    logger.info("🔄 Запускаю фолбэк проверку...")
    check_interval = 300
    
    while True:
        time.sleep(check_interval)
        
        try:
            logger.info("🔍 Выполняю фолбэк проверку каналов...")
            
            for webhook_url, config in CHANNEL_CONFIGS.items():
                if not config.get('in_burst_mode', False) and config.get('channel_id'):
                    messages = fetch_discord_channel_messages(config['channel_id'])
                    if messages:
                        for message in messages[:3]:
                            process_discord_message(message, webhook_url, config['channel_id'])
            
        except Exception as e:
            logger.error(f"❌ Ошибка фолбэк проверки: {e}")

# ==================== ПРОСТОЙ САМОПИНГ ====================
def simple_self_pinger():
    global ping_count, last_ping_time
    
    logger.info("🏓 Запускаю простой самопинг...")
    time.sleep(30)
    
    while True:
        try:
            ping_count += 1
            last_ping_time = datetime.now()
            logger.info(f"🏓 Самопинг #{ping_count} в {last_ping_time.strftime('%H:%M:%S')}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
        
        time.sleep(300)

# ==================== TELEGRAM КОМАНДЫ ====================
def telegram_poller():
    global telegram_offset
    
    logger.info("🤖 Запускаю Telegram поллер...")
    time.sleep(10)
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {
                'offset': telegram_offset + 1,
                'timeout': 10,
                'limit': 1
            }
            
            response = requests.get(url, params=params, timeout=15)
            
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
                            
                            if 'sticker' in message:
                                sticker = message['sticker']
                                file_id = sticker['file_id']
                                emoji = sticker.get('emoji', '')
                                
                                sticker_info = (
                                    f"🎯 <b>Информация о стикере:</b>\n"
                                    f"🆔 File ID: <code>{file_id}</code>\n"
                                    f"😊 Emoji: {emoji}"
                                )
                                send_telegram_message(chat_id, sticker_info)
                                continue
                            
                            if text.startswith('/'):
                                handle_telegram_command(chat_id, text)
            
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"❌ Ошибка Telegram поллера: {e}")
            time.sleep(10)

def handle_telegram_command(chat_id, command):
    global channel_enabled
    
    logger.info(f"🎯 Команда от {chat_id}: {command}")
    
    if command == '/start':
        seeds_list = "\n".join([f"{config['emoji']} {config['display_name']}" 
                              for config in TARGET_SEEDS.values()])
        
        channels_info = "\n".join([f"{config['name']}" 
                                 for config in CHANNEL_CONFIGS.values()])
        
        welcome_text = (
            "🚀 <b>НОВАЯ ВЕРСИЯ С ВЕБХУКАМИ!</b>\n\n"
            "📡 <b>Мониторю через вебхуки:</b>\n"
            f"{channels_info}\n\n"
            "⚡ <b>Новая логика:</b>\n"
            "1. Получаю сообщения мгновенно через вебхуки\n"
            "2. После сообщения запускаю серию запросов\n"
            "3. Экономлю запросы к Discord API\n\n"
            "📱 <b>Вам в бота:</b> Все сообщения от Kiro\n"
            "📢 <b>В канал:</b> Стикеры при редких предметах\n\n"
            f"🎯 <b>Отслеживаю:</b>\n"
            f"{seeds_list}\n\n"
            "🛡️ <b>Защита от спама:</b> 2 сек между сообщениями\n"
            "🏓 <b>Самопинг:</b> Каждые 5 минут\n\n"
            "📋 <b>Команды:</b>\n"
            "/status - Статус бота\n"
            "/enable - Включить канал\n"
            "/disable - Выключить канал\n"
            "/help - Помощь"
        )
        send_telegram_message(chat_id, welcome_text)
    
    elif command == '/status':
        send_bot_status(chat_id)
    
    elif command == '/enable':
        channel_enabled = True
        send_telegram_message(chat_id, "✅ <b>Канал ВКЛЮЧЕН</b>")
    
    elif command == '/disable':
        channel_enabled = False
        send_telegram_message(chat_id, "⏸️ <b>Канал ВЫКЛЮЧЕН</b>")
    
    elif command == '/help':
        help_text = (
            "📋 <b>Доступные команды:</b>\n\n"
            "/start - Информация о боте\n"
            "/status - Статус и статистика\n"
            "/enable - Включить уведомления в канал\n"
            "/disable - Выключить уведомления в канал\n"
            "/help - Эта справка"
        )
        send_telegram_message(chat_id, help_text)
    
    else:
        send_telegram_message(chat_id, "❌ Неизвестная команда. Используйте /help")

def send_bot_status(chat_id):
    global bot_status, last_error, channel_enabled, ping_count, last_ping_time, found_seeds_count
    
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    last_ping_str = "Еще не было" if not last_ping_time else last_ping_time.strftime('%H:%M:%S')
    
    seeds_stats = "\n".join([f"{config['emoji']} {config['display_name']}: {found_seeds_count.get(name, 0)} раз" 
                           for name, config in TARGET_SEEDS.items()])
    
    channels_info = []
    for config in CHANNEL_CONFIGS.values():
        channel_id_status = "✅" if config.get('channel_id') else "❌"
        burst_status = "🟢 Активен" if config.get('in_burst_mode', False) else "⚪ Ожидание"
        channels_info.append(f"{config['name']}: {burst_status} (ID: {channel_id_status})")
    
    status_text = (
        f"📊 <b>Статус бота (Вебхуки)</b>\n\n"
        f"{bot_status}\n"
        f"⏰ Время работы: {hours:.1f} часов\n"
        f"📅 Запущен: {startup_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"📡 Каналов: {len(CHANNEL_CONFIGS)} шт\n"
        f"🏓 Самопинг: {ping_count} раз (последний: {last_ping_str})\n"
        f"💾 В кэше: {len(processed_messages_cache)} сообщений\n\n"
        f"📡 <b>Статус каналов:</b>\n" + "\n".join(channels_info) + "\n\n"
        f"🎯 <b>Найдено предметов:</b>\n"
        f"{seeds_stats}"
    )
    
    if last_error:
        status_text += f"\n\n⚠️ <b>Последняя ошибка:</b>\n<code>{last_error}</code>"
    
    send_telegram_message(chat_id, status_text)

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    seeds_list = ", ".join([f"{config['emoji']} {config['display_name']}" 
                          for config in TARGET_SEEDS.values()])
    
    channels_list = []
    for config in CHANNEL_CONFIGS.values():
        channel_id_status = "✅ Настроен" if config.get('channel_id') else "⏳ Жду вебхук"
        channels_list.append(f"• {config['name']} - {channel_id_status}")
    
    channels_info = "\n".join(channels_list)
    
    return f"""
    <html>
        <head>
            <title>🌱 Seed Monitor (Webhooks)</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                .status {{ background: #f0f8f0; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .info {{ margin: 10px 0; }}
                .channels {{ background: #e3f2fd; padding: 20px; margin: 10px 0; border-radius: 8px; }}
                .seeds {{ background: #f3e5f5; padding: 20px; margin: 10px 0; border-radius: 8px; }}
                .button {{ background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block; }}
                .button-disable {{ background: #f44336; }}
                .webhook-info {{ background: #fff3e0; padding: 15px; border-radius: 8px; margin: 15px 0; }}
                .status-good {{ color: green; }}
                .status-waiting {{ color: orange; }}
            </style>
        </head>
        <body>
            <h1>🌱 Мониторинг семян (Webhooks)</h1>
            
            <div class="status">
                <h3>📊 Статус системы</h3>
                <div class="info"><strong>Состояние:</strong> {bot_status}</div>
                <div class="info"><strong>Время работы:</strong> {hours:.1f} часов</div>
                <div class="info"><strong>Канал:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</div>
                <div class="info"><strong>Самопинг:</strong> 🏓 {ping_count} раз</div>
                <div class="info"><strong>В кэше:</strong> {len(processed_messages_cache)} сообщений</div>
            </div>
            
            <div class="channels">
                <h3>📡 Отслеживаемые каналы</h3>
                <pre>{channels_info}</pre>
            </div>
            
            <div class="seeds">
                <h3>🎯 Отслеживаемые предметы</h3>
                <div class="info">{seeds_list}</div>
            </div>
            
            <div class="webhook-info">
                <h3>⚡ Webhooks</h3>
                <p>Бот получает сообщения мгновенно через Discord Webhooks.</p>
                <p>После первого сообщения от Kiro автоматически определит ID каналов.</p>
            </div>
            
            <div>
                <h3>🎛️ Управление</h3>
                <a href="/enable_channel" class="button">✅ Включить канал</a>
                <a href="/disable_channel" class="button button-disable">⏸️ Выключить канал</a>
                <a href="/health" class="button">🩺 Health Check</a>
            </div>
        </body>
    </html>
    """

@app.route('/enable_channel')
def enable_channel_route():
    global channel_enabled
    channel_enabled = True
    return "✅ Уведомления в канал ВКЛЮЧЕНЫ"

@app.route('/disable_channel')
def disable_channel_route():
    global channel_enabled
    channel_enabled = False
    return "⏸️ Уведомления в канал ВЫКЛЮЧЕНЫ"

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime': (datetime.now() - startup_time).total_seconds(),
        'channels_configured': len(CHANNEL_CONFIGS),
        'channels_with_id': sum(1 for config in CHANNEL_CONFIGS.values() if config.get('channel_id'))
    })

# ==================== ЗАПУСК ====================
def start_background_threads():
    threads = []
    
    worker_thread = threading.Thread(target=queue_worker, daemon=True, name="QueueWorker")
    threads.append(worker_thread)
    
    fallback_thread = threading.Thread(target=fallback_checker, daemon=True, name="FallbackChecker")
    threads.append(fallback_thread)
    
    pinger_thread = threading.Thread(target=simple_self_pinger, daemon=True, name="SelfPinger")
    threads.append(pinger_thread)
    
    telegram_thread = threading.Thread(target=telegram_poller, daemon=True, name="TelegramPoller")
    threads.append(telegram_thread)
    
    for thread in threads:
        thread.start()
        time.sleep(1)
        logger.info(f"✅ Запущен поток: {thread.name}")
    
    return threads

if __name__ == '__main__':
    # Проверяем обязательные переменные
    required_vars = ['TELEGRAM_TOKEN', 'TELEGRAM_CHANNEL_ID', 'TELEGRAM_BOT_CHAT_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Отсутствуют переменные: {', '.join(missing_vars)}")
    
    webhooks_count = sum(1 for url in [WEBHOOK_SEEDS_URL, WEBHOOK_EGGS_URL, WEBHOOK_PASS_SHOP_URL] if url)
    logger.info(f"🌐 Настроено {webhooks_count} вебхуков")
    
    if not CHANNEL_CONFIGS:
        logger.error("❌ Нет настроенных каналов! Проверьте вебхуки.")
    else:
        logger.info(f"📡 Каналы для мониторинга:")
        for url, config in CHANNEL_CONFIGS.items():
            logger.info(f"  • {config['name']}")
    
    seeds_count = len(TARGET_SEEDS)
    logger.info(f"🚀 Запуск бота с вебхуками")
    logger.info(f"🎯 Отслеживаю {seeds_count} предметов")
    logger.info(f"📡 Вебхук эндпоинт: /discord_webhook")
    logger.info(f"🏓 Самопинг: каждые 5 минут")
    
    threads = start_background_threads()
    
    try:
        startup_msg = (
            "🚀 <b>БОТ ЗАПУЩЕН С ВЕБХУКАМИ!</b>\n\n"
            f"📡 <b>Мониторю каналы:</b> {len(CHANNEL_CONFIGS)}\n"
            f"🎯 <b>Отслеживаю предметы:</b> {len(TARGET_SEEDS)}\n"
            f"⚡ <b>Логика:</b> Вебхуки + burst запросы\n\n"
            "📝 <b>Статус:</b> Жду первое сообщение от Kiro для определения ID каналов\n\n"
            "✅ <b>Готов к работе!</b>\n"
            "Отправьте /status для проверки."
        )
        send_to_bot(startup_msg)
    except Exception as e:
        logger.error(f"❌ Не удалось отправить стартовое сообщение: {e}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
