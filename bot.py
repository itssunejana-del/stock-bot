from flask import Flask, request
import requests
import os
import time
import logging
import threading
from datetime import datetime
import re
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Токены и ID
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# 🆕 МНОЖЕСТВЕННЫЕ КАНАЛЫ - получаем список ID
DISCORD_CHANNEL_IDS_STR = os.getenv('DISCORD_CHANNEL_IDS', '')
if DISCORD_CHANNEL_IDS_STR:
    DISCORD_CHANNEL_IDS = [ch.strip() for ch in DISCORD_CHANNEL_IDS_STR.split(',') if ch.strip()]
    logger.info(f"📡 Настроено {len(DISCORD_CHANNEL_IDS)} каналов для мониторинга")
else:
    # Для обратной совместимости
    DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
    if DISCORD_CHANNEL_ID:
        DISCORD_CHANNEL_IDS = [DISCORD_CHANNEL_ID]
        logger.info(f"📡 Использую один канал (старая конфигурация)")
    else:
        DISCORD_CHANNEL_IDS = []
        logger.error("❌ Не указаны каналы Discord!")

RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')

# 🆕 Настройки отслеживаемых семян
TARGET_SEEDS = {
    'octobloom': {
        'keywords': ['octobloom', 'октоблум', ':octobloom'],
        'sticker_id': "CAACAgIAAxkBAAEP1btpIXhIEvgVEK4c6ugJv1EgP7UY-wAChokAAtZpCElVMcRUgb_jdDYE",
        'emoji': '🐙',
        'display_name': 'Octobloom'
    },
    'gem_egg': {
        'keywords': ['gem egg', 'gemegg', ':gemegg'],
        'sticker_id': "CAACAgIAAxkBAAEP1b9pIXhSl-ElpsKgOEEY-8oOmJ1qnAACI4MAAq6w2EinW-vu8EV_RzYE",
        'emoji': '💎',
        'display_name': 'Gem Egg'
    },
    'crimson_thorn': {
        'keywords': ['crimson thorn', 'crimsonthorn', ':crimsonthorn', ':crimsonthon'],
        'sticker_id': "CAACAgIAAxkBAAEPtExpCrIew_M01f5h8MyaGyeMKAABiiEAAvmLAALkoFhIP2bLUVXqoWU2BA",
        'emoji': '🌵',
        'display_name': 'Crimson Thorn'
    },
    'zebrazinkle': {
        'keywords': ['zebrazinkle', 'zebra zinkle', ':zebrazinkle'],
        'sticker_id': "CAACAgIAAxkBAAEPwjJpFDhW_6Vu29vF7DrTHFBcSf_WIAAC1XkAAkCXoUgr50G4SlzwrzYE",
        'emoji': '🦓',
        'display_name': 'Zebrazinkle'
    }
}

# 🆕 Глобальные переменные для множественных каналов
last_processed_ids = {}  # Словарь: {channel_id: last_message_id}
CACHE_FILE = '/tmp/last_processed_ids.json'  # 🆕 Используем /tmp/ директорию (доступную для записи в Render)
startup_time = datetime.now()
channel_enabled = True
bot_status = "🟢 Работает нормально"
last_error = None
processed_messages_cache = set()
telegram_offset = 0
ping_count = 0
last_ping_time = None
found_seeds_count = {name: 0 for name in TARGET_SEEDS.keys()}

def save_last_processed_ids():
    """Сохраняет последние обработанные ID для всех каналов"""
    try:
        # Создаем словарь для сохранения
        save_data = {
            'last_processed_ids': last_processed_ids,
            'saved_at': datetime.now().isoformat()
        }
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(save_data, f, indent=2)
        
        logger.info(f"💾 Сохранены last_processed_ids для {len(last_processed_ids)} каналов в {CACHE_FILE}")
        logger.debug(f"💾 Данные: {json.dumps(last_processed_ids, indent=2)}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения кэша: {e}")
        # Пробуем альтернативный путь
        try:
            alt_path = './last_processed_ids.json'
            with open(alt_path, 'w') as f:
                json.dump({'last_processed_ids': last_processed_ids}, f)
            logger.info(f"💾 Сохранено в альтернативный путь: {alt_path}")
        except Exception as alt_e:
            logger.error(f"❌ Ошибка альтернативного сохранения: {alt_e}")

def load_last_processed_ids():
    """Загружает последние обработанные ID для всех каналов"""
    try:
        # Пробуем основной путь
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                loaded_ids = data.get('last_processed_ids', {})
                logger.info(f"📂 Загружены last_processed_ids для {len(loaded_ids)} каналов из {CACHE_FILE}")
                logger.debug(f"📂 Данные: {json.dumps(loaded_ids, indent=2)}")
                return loaded_ids
        
        # Пробуем альтернативный путь
        alt_path = './last_processed_ids.json'
        if os.path.exists(alt_path):
            with open(alt_path, 'r') as f:
                data = json.load(f)
                loaded_ids = data.get('last_processed_ids', {})
                logger.info(f"📂 Загружены last_processed_ids для {len(loaded_ids)} каналов из {alt_path}")
                return loaded_ids
        
        logger.info("📂 Файл кэша не найден, начинаем с начала")
        return {}
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки кэша: {e}")
        return {}

def cleanup_memory_cache():
    """Умная очистка оперативной памяти"""
    global processed_messages_cache
    
    if len(processed_messages_cache) > 200:
        old_size = len(processed_messages_cache)
        recent_messages = list(processed_messages_cache)[-100:]
        processed_messages_cache = set(recent_messages)
        logger.info(f"🧹 Очистил кэш: {old_size} -> {len(processed_messages_cache)} сообщений")

def self_pinger():
    """Самопинг чтобы Render не останавливал сервис"""
    global ping_count, last_ping_time
    
    logger.info("🔄 Запускаю самопинг...")
    
    time.sleep(30)
    
    while True:
        try:
            ping_count += 1
            last_ping_time = datetime.now()
            logger.info(f"🏓 Самопинг #{ping_count}...")
            
            response = requests.get(f"{RENDER_SERVICE_URL}/", timeout=10)
            if response.status_code == 200:
                logger.info("✅ Самопинг успешен - сервис активен")
            else:
                logger.warning(f"⚠️ Самопинг: статус {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
        
        logger.info("💤 Ожидаю 8 минут до следующего самопинга...")
        time.sleep(480)

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
        response = requests.post(url, data=data, timeout=15)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено в Telegram ({chat_id}): {text[:100]}...")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def send_telegram_sticker(chat_id, sticker_id):
    """Отправляет стикер в Telegram"""
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены переменные Telegram")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {
            "chat_id": chat_id, 
            "sticker": sticker_id
        }
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
    """Отправляет сообщение или стикер в ТЕЛЕГРАМ КАНАЛ"""
    if not channel_enabled:
        logger.info("⏸️ Канал отключен, сообщение не отправлено")
        return False
    
    if not hasattr(send_to_channel, 'last_channel_message_time'):
        send_to_channel.last_channel_message_time = 0
    
    current_time = time.time()
    
    time_since_last = current_time - send_to_channel.last_channel_message_time
    if time_since_last < 2 and time_since_last >= 0:
        wait_time = 2 - time_since_last
        logger.info(f"⏸️ Защита от спама: жду {wait_time:.1f} сек")
        time.sleep(wait_time)
    
    send_to_channel.last_channel_message_time = current_time
        
    if sticker_id:
        return send_telegram_sticker(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    else:
        return False

def send_to_bot(text):
    """Отправляет сообщение в ТЕЛЕГРАМ БОТА"""
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

def send_help_message(chat_id):
    """Отправляет сообщение со списком команд"""
    seeds_list = "\n".join([f"{config['emoji']} {config['display_name']}" for name, config in TARGET_SEEDS.items()])
    
    help_text = (
        f"🤖 <b>Бот мониторинга Grow a Garden</b>\n\n"
        f"📋 <b>Доступные команды:</b>\n"
        f"/start - Начать работу\n"
        f"/status - Статус бота\n" 
        f"/enable - Включить уведомления в канал\n"
        f"/disable - Выключить уведомления в канал\n"
        f"/help - Показать это сообщение\n\n"
        f"🎯 <b>Отслеживаю семена:</b>\n"
        f"{seeds_list}\n\n"
        f"📡 <b>Мониторю каналы:</b> {len(DISCORD_CHANNEL_IDS)} шт\n"
        f"🔄 Бот автоматически отслеживает стоки из нескольких Discord каналов."
    )
    send_telegram_message(chat_id, help_text)

def send_bot_status(chat_id):
    """Отправляет статус бота"""
    global bot_status, last_error, channel_enabled, ping_count, last_ping_time, found_seeds_count, last_processed_ids
    
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    last_ping_str = "Еще не было" if not last_ping_time else last_ping_time.strftime('%H:%M:%S')
    
    seeds_stats = "\n".join([f"{TARGET_SEEDS[name]['emoji']} {TARGET_SEEDS[name]['display_name']}: {count} раз" 
                           for name, count in found_seeds_count.items()])
    
    # Информация о каналах
    channels_info = []
    for channel_id in DISCORD_CHANNEL_IDS:
        last_id = last_processed_ids.get(channel_id, 'Нет данных')
        channel_short = channel_id[-6:] if len(channel_id) > 6 else channel_id
        channels_info.append(f"📡 Канал {channel_short}: {last_id}")
    
    # Информация о файле кэша
    cache_exists = os.path.exists(CACHE_FILE)
    alt_cache_exists = os.path.exists('./last_processed_ids.json')
    cache_info = f"📁 Кэш: {'✅' if cache_exists else '❌'}{' (альт: ✅)' if alt_cache_exists else ''}"
    
    status_text = (
        f"📊 <b>Статус бота</b>\n\n"
        f"{bot_status}\n"
        f"⏰ Время работы: {hours:.1f} часов\n"
        f"📅 Запущен: {startup_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"📡 Отслеживаю: {len(DISCORD_CHANNEL_IDS)} каналов\n"
        f"{cache_info}\n"
        f"🏓 Самопинг: {ping_count} раз (последний: {last_ping_str})\n"
        f"📝 В памяти: {len(processed_messages_cache)} сообщений\n\n"
        f"🎯 <b>Найдено семян:</b>\n"
        f"{seeds_stats}\n\n"
        f"📡 <b>Статус каналов:</b>\n" + "\n".join(channels_info)
    )
    
    if last_error:
        status_text += f"\n\n⚠️ <b>Последняя ошибка:</b>\n<code>{last_error}</code>"
    
    send_telegram_message(chat_id, status_text)

def handle_telegram_command(chat_id, command, message=None):
    """Обрабатывает команды Telegram"""
    global channel_enabled
    
    logger.info(f"🎯 Обрабатываю команду: {command} от {chat_id}")
    
    if message and 'sticker' in message:
        sticker = message['sticker']
        file_id = sticker['file_id']
        emoji = sticker.get('emoji', '')
        
        sticker_info = (
            f"🎯 <b>Информация о стикере:</b>\n"
            f"🆔 File ID: <code>{file_id}</code>\n"
            f"😊 Emoji: {emoji}\n\n"
            f"📋 <b>Для использования в коде:</b>\n"
            f"<code>sticker_id = \"{file_id}\"</code>"
        )
        send_telegram_message(chat_id, sticker_info)
        return
    
    if command == '/start':
        seeds_list = "\n".join([f"{config['emoji']} {config['display_name']}" for name, config in TARGET_SEEDS.items()])
        
        welcome_text = (
            "🎮 <b>Добро пожаловать!</b>\n\n"
            "Я бот для отслеживания стоков в игре <b>Grow a Garden</b>.\n"
            f"Автоматически мониторю <b>{len(DISCORD_CHANNEL_IDS)} Discord каналов</b> и присылаю уведомления о стоках.\n\n"
            "📱 <b>Вам в личные сообщения:</b> Все стоки (читабельный текст)\n"
            "📢 <b>В канал:</b> Только стикеры при редких семенах\n"
            "🏓 <b>Самопинг:</b> Активен (каждые 8 минут)\n"
            "💾 <b>Умный кэш:</b> Сохраняет состояние между перезапусками\n"
            "🛡️ <b>Защита от спама:</b> Автоматические паузы между сообщениями\n"
            "📊 <b>Авто-статус:</b> Каждые 5 часов\n\n"
            f"🎯 <b>Отслеживаю семена:</b>\n"
            f"{seeds_list}\n\n"
            f"📡 <b>Мониторю каналы:</b> {len(DISCORD_CHANNEL_IDS)} шт\n\n"
            "🎯 <b>Чтобы получить ID стикера:</b> Просто отправьте мне любой стикер!\n\n"
            "Используйте /help для списка команд."
        )
        send_telegram_message(chat_id, welcome_text)
        
    elif command == '/help':
        send_help_message(chat_id)
        
    elif command == '/status':
        send_bot_status(chat_id)
        
    elif command == '/enable':
        channel_enabled = True
        send_telegram_message(chat_id, "✅ <b>Уведомления в канал ВКЛЮЧЕНЫ</b>\nТеперь стикеры будут приходить в канал при обнаружении семян.")
        
    elif command == '/disable':
        channel_enabled = False
        send_telegram_message(chat_id, "⏸️ <b>Уведомления в канал ВЫКЛЮЧЕНЫ</b>\nУведомления о семенах (стикеры) временно приостановлены.")
        
    else:
        send_telegram_message(chat_id, "❌ Неизвестная команда. Используйте /help для списка команд.")

def telegram_poller_safe():
    """Безопасный опросщик Telegram"""
    global telegram_offset
    
    logger.info("🔍 Запускаю Telegram поллер...")
    
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
                                logger.info("📎 Получен стикер, обрабатываю...")
                                handle_telegram_command(chat_id, None, message)
                                continue
                                
                            if text.startswith('/'):
                                handle_telegram_command(chat_id, text)
                
                time.sleep(5)
                
            elif response.status_code == 409:
                logger.warning("⚠️ Конфликт с другим экземпляром. Жду 60 секунд...")
                time.sleep(60)
            else:
                logger.error(f"❌ Ошибка Telegram API: {response.status_code}")
                time.sleep(10)
            
        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            logger.error(f"💥 Ошибка в телеграм поллере: {e}")
            time.sleep(10)

def get_discord_messages():
    """🆕 Получает сообщения из МНОЖЕСТВА Discord каналов"""
    all_messages = []
    
    for channel_id in DISCORD_CHANNEL_IDS:
        try:
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=10"
            headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                messages = response.json()
                # Добавляем информацию о канале к каждому сообщению
                for msg in messages:
                    msg['source_channel_id'] = channel_id
                all_messages.extend(messages)
                logger.debug(f"✅ Получено {len(messages)} сообщений из канала {channel_id[-6:]}")
            else:
                logger.error(f"❌ Ошибка Discord API для канала {channel_id[-6:]}: {response.status_code}")
                
        except Exception as e:
            logger.error(f"💥 Ошибка подключения к каналу {channel_id[-6:]}: {e}")
    
    return all_messages

def clean_ember_text_for_display(text):
    """Очищает текст для красивого отображения в Telegram"""
    text = re.sub(r'<:[a-zA-Z0-9_]+:(\d+)>', '', text)
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'<t:\d+:[tR]>', '', text)
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if line and ('x' in line or ':' in line or any(word in line.lower() for word in ['seeds', 'gear', 'alert'])):
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def extract_all_text_from_message(message):
    """Извлекает ВЕСЬ текст из сообщения"""
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

def format_ember_message_for_bot(message):
    """Форматирует сообщение для Telegram бота"""
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
    
    cleaned_text = clean_ember_text_for_display(full_text)
    
    return cleaned_text.strip()

def check_ember_messages(messages):
    """🆕 УПРОЩЕННАЯ версия проверки сообщений - РАБОЧАЯ"""
    global last_processed_ids, bot_status, last_error, processed_messages_cache, found_seeds_count
    
    if not messages:
        return False
    
    try:
        found_any_seed = False
        
        # Инициализируем last_processed_ids при первом запуске
        if not last_processed_ids:
            last_processed_ids = load_last_processed_ids()
            logger.info(f"📂 Загружены last_processed_ids для {len(last_processed_ids)} каналов")
        
        # Проходим по всем сообщениям
        for message in messages:
            try:
                message_id = str(message.get('id', ''))
                if not message_id:
                    continue
                    
                channel_id = str(message.get('source_channel_id', 'unknown'))
                
                # Создаем уникальный ключ для кэша
                cache_key = f"{channel_id}:{message_id}"
                
                # Проверяем дубликаты в кэше памяти
                if cache_key in processed_messages_cache:
                    continue
                
                # Получаем информацию об авторе
                author_info = message.get('author', {})
                author_name = str(author_info.get('username', '')).lower()
                author_global_name = str(author_info.get('global_name', '')).lower()
                
                # Проверяем, является ли автор ботом
                is_bot = message.get('author', {}).get('bot', False)
                is_ember = 'ember' in author_name or 'ember' in author_global_name
                is_bot_like = 'bot' in author_name or 'бот' in author_name
                
                if not (is_bot or is_ember or is_bot_like):
                    continue
                
                # Добавляем в кэш памяти
                processed_messages_cache.add(cache_key)
                
                # Получаем текст сообщения
                full_text = extract_all_text_from_message(message)
                
                # Форматируем для отправки боту
                formatted_message = format_ember_message_for_bot(message)
                
                if formatted_message:
                    # Отправляем сообщение боту
                    current_time = datetime.now().strftime('%H:%M:%S')
                    channel_short = channel_id[-6:] if len(channel_id) > 6 else channel_id
                    author_display = author_info.get('global_name') or author_info.get('username', 'Unknown')
                    bot_message = (
                        f"🤖 Автор: {author_display}\n"
                        f"📡 Канал: {channel_short}\n"
                        f"🕒 Время: {current_time}\n\n"
                        f"<code>{formatted_message}</code>"
                    )
                    send_to_bot(bot_message)
                    
                    # Проверяем наличие семян
                    text_lower = full_text.lower()
                    for seed_name, seed_config in TARGET_SEEDS.items():
                        for keyword in seed_config['keywords']:
                            if keyword in text_lower:
                                found_seeds_count[seed_name] += 1
                                logger.info(f"🎯 Найден {seed_name.upper()} в канале {channel_short}!")
                                
                                # Отправляем стикер в канал
                                sticker_sent = send_to_channel(sticker_id=seed_config['sticker_id'])
                                
                                if sticker_sent:
                                    send_to_bot(f"✅ Стикер {seed_config['emoji']} отправлен в канал")
                                    logger.info(f"✅ Стикер о {seed_name} отправлен в канал!")
                                else:
                                    send_to_bot(f"❌ Стикер {seed_config['emoji']} не отправлен в канал")
                                    logger.error(f"❌ Ошибка отправки стикера о {seed_name}")
                                
                                found_any_seed = True
                                break
                
                # Обновляем last_processed_id для этого канала
                last_processed_ids[channel_id] = message_id
                
                # 🆕 Сохраняем кэш после каждого обработанного сообщения
                save_last_processed_ids()
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения: {e}")
                continue
        
        bot_status = "🟢 Работает нормально"
        last_error = None
        return found_any_seed
        
    except Exception as e:
        error_msg = f"Ошибка обработки сообщений: {e}"
        logger.error(f"💥 {error_msg}")
        bot_status = "🔴 Ошибка обработки"
        last_error = error_msg
        send_to_bot(f"🚨 <b>Ошибка в мониторинге:</b>\n<code>{last_error}</code>")
        return False

def monitor_discord():
    """Основная функция мониторинга - для множества каналов"""
    logger.info(f"🔄 Запуск мониторинга {len(DISCORD_CHANNEL_IDS)} каналов Discord...")
    
    if not DISCORD_CHANNEL_IDS:
        logger.error("❌ Нет каналов для мониторинга!")
        send_to_bot("❌ <b>ОШИБКА:</b> Не указаны каналы Discord для мониторинга!")
        return
    
    error_count = 0
    max_errors = 5
    
    # 🆕 Проверяем доступность записи в файл
    try:
        test_file = '/tmp/test_write.txt'
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        logger.info("✅ Проверка записи в /tmp/ прошла успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка записи в /tmp/: {e}")
    
    while True:
        try:
            messages = get_discord_messages()
            
            if messages:
                found_any_seed = check_ember_messages(messages)
                cleanup_memory_cache()
                
                if found_any_seed:
                    logger.info("✅ Стикер о семенах отправлен в канал!")
                
                error_count = 0
            else:
                error_count += 1
                cleanup_memory_cache()
                
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
    logger.info("❤️ Запускаю монитор здоровья (каждые 5 часов)...")
    
    report_count = 0
    
    while True:
        try:
            time.sleep(18000)
            
            report_count += 1
            uptime = datetime.now() - startup_time
            hours = uptime.total_seconds() / 3600
            
            seeds_stats = "\n".join([f"{TARGET_SEEDS[name]['emoji']} {TARGET_SEEDS[name]['display_name']}: {count} раз" 
                                   for name, count in found_seeds_count.items()])
            
            # Проверяем файл кэша
            cache_exists = os.path.exists(CACHE_FILE)
            cache_size = os.path.getsize(CACHE_FILE) if cache_exists else 0
            
            status_report = (
                f"📊 <b>Авто-статус #{report_count}</b>\n"
                f"⏰ Работает: {hours:.1f} часов\n"
                f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
                f"📡 Каналов: {len(DISCORD_CHANNEL_IDS)} шт\n"
                f"📁 Кэш: {'✅' if cache_exists else '❌'} ({cache_size} байт)\n"
                f"🔄 {bot_status}\n"
                f"🏓 Самопинг: {ping_count} раз\n"
                f"📝 В памяти: {len(processed_messages_cache)} сообщений\n\n"
                f"🎯 <b>Найдено семян:</b>\n"
                f"{seeds_stats}\n\n"
                f"✅ Бот стабильно работает"
            )
            
            send_to_bot(status_report)
            logger.info(f"📊 Авто-статус #{report_count} отправлен в бота")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки авто-статуса: {e}")

@app.route('/')
def home():
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    seeds_list = ", ".join([f"{config['emoji']} {config['display_name']}" for name, config in TARGET_SEEDS.items()])
    
    # Информация о каналах
    channels_info = ""
    for i, channel_id in enumerate(DISCORD_CHANNEL_IDS[:5], 1):  # Показываем первые 5
        channel_short = channel_id[-6:] if len(channel_id) > 6 else channel_id
        last_id = last_processed_ids.get(channel_id, 'Нет данных')
        channels_info += f"<div class='info'><strong>Канал {i}:</strong> ...{channel_short} (последний: {last_id})</div>"
    
    if len(DISCORD_CHANNEL_IDS) > 5:
        channels_info += f"<div class='info'><strong>И еще:</strong> {len(DISCORD_CHANNEL_IDS) - 5} каналов</div>"
    
    # Информация о файле кэша
    cache_exists = os.path.exists(CACHE_FILE)
    alt_cache_exists = os.path.exists('./last_processed_ids.json')
    cache_info = f"<div class='info'><strong>Файл кэша:</strong> {'✅ Существует' if cache_exists else '❌ Не найден'} (путь: {CACHE_FILE})</div>"
    if alt_cache_exists:
        cache_info += f"<div class='info'><strong>Альтернативный кэш:</strong> ✅ Существует</div>"
    
    return f"""
    <html>
        <head>
            <title>🌱 Seed Monitor</title>
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
            <h1>🌱 Умный мониторинг семян</h1>
            
            <div class="status">
                <h3>📊 Статус системы</h3>
                <div class="info"><strong>Состояние:</strong> {bot_status}</div>
                <div class="info"><strong>Время работы:</strong> {hours:.1f} часов</div>
                <div class="info"><strong>Канал:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</div>
                <div class="info"><strong>Каналов Discord:</strong> {len(DISCORD_CHANNEL_IDS)} шт</div>
                <div class="info"><strong>Самопинг:</strong> 🏓 {ping_count} раз</div>
                <div class="info"><strong>В памяти:</strong> {len(processed_messages_cache)} сообщений</div>
                <div class="info"><strong>Авто-статус:</strong> 📊 Каждые 5 часов</div>
                <div class="info"><strong>Отслеживаю:</strong> {seeds_list}</div>
                {cache_info}
                <h4>📡 Отслеживаемые каналы:</h4>
                {channels_info}
            </div>
            
            <div class="commands">
                <h3>🎛️ Управление</h3>
                <a href="/enable_channel" class="button">✅ Включить канал</a>
                <a href="/disable_channel" class="button button-disable">⏸️ Выключить канал</a>
                <a href="/status" class="button">📊 Статус</a>
            </div>
            
            <div class="commands">
                <h3>🤖 Логика работы</h3>
                <p>📱 <strong>Вам в бота:</strong> Все стоки из {len(DISCORD_CHANNEL_IDS)} каналов</p>
                <p>📢 <strong>В канал:</strong> Только стикеры при редких семенах</p>
                <p>🎯 <strong>Отслеживаю:</strong> {seeds_list}</p>
                <p>📡 <strong>Множественный мониторинг:</strong> Поддерживает несколько Discord каналов</p>
                <p>💾 <strong>Умный кэш:</strong> Сохраняет состояние для каждого канала</p>
                <p>🛡️ <strong>Защита от спама:</strong> Автоматические паузы между сообщениями</p>
                <p>🏓 <strong>Самопинг:</strong> Каждые 8 минут</p>
                <p>📊 <strong>Авто-статус:</strong> Каждые 5 часов</p>
            </div>
        </body>
    </html>
    """

@app.route('/enable_channel')
def enable_channel():
    global channel_enabled
    channel_enabled = True
    return "✅ Уведомления в канал ВКЛЮЧЕНЫ"

@app.route('/disable_channel')
def disable_channel():
    global channel_enabled
    channel_enabled = False
    return "⏸️ Уведомления в канал ВЫКЛЮЧЕНЫ"

@app.route('/status')
def status_page():
    return home()

def start_background_threads():
    logger.info("🔄 Запускаю фоновые потоки...")
    
    threads = [
        threading.Thread(target=monitor_discord, daemon=True),
        threading.Thread(target=telegram_poller_safe, daemon=True),
        threading.Thread(target=health_monitor, daemon=True),
        threading.Thread(target=self_pinger, daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Поток {thread.name} запущен")
    
    return threads

if __name__ == '__main__':
    seeds_list = ", ".join([f"{config['emoji']} {config['display_name']}" for name, config in TARGET_SEEDS.items()])
    
    logger.info("🚀 ЗАПУСК БОТА С МНОЖЕСТВЕННЫМ МОНИТОРИНГОМ!")
    logger.info(f"📡 Мониторю: {len(DISCORD_CHANNEL_IDS)} каналов Discord")
    logger.info("📱 Вам в бота: Все стоки из всех каналов")
    logger.info("📢 В канал: Только стикеры при редких семенах")
    logger.info(f"🎯 Отслеживаю: {seeds_list}")
    logger.info(f"📁 Путь к кэшу: {CACHE_FILE}")
    logger.info("🛡️ Защита от спама: Активна (2 сек между сообщениями)")
    logger.info("🧹 Умная очистка памяти: Активна")
    logger.info("🏓 Самопинг: Активен (каждые 8 минут)")
    logger.info("📊 Авто-статус: Каждые 5 часов")
    
    # Проверяем директорию /tmp/
    try:
        import tempfile
        temp_dir = tempfile.gettempdir()
        logger.info(f"📁 Временная директория системы: {temp_dir}")
    except:
        pass
    
    start_background_threads()
    
    seeds_list_bot = "\n".join([f"{config['emoji']} {config['display_name']}" for name, config in TARGET_SEEDS.items()])
    
    startup_msg_bot = (
        f"🚀 <b>БОТ ЗАПУЩЕН С МНОЖЕСТВЕННЫМ МОНИТОРИНГОМ!</b>\n\n"
        f"📡 <b>Мониторю:</b> {len(DISCORD_CHANNEL_IDS)} каналов Discord\n"
        f"📱 <b>Вам в бота:</b> Все стоки из всех каналов\n"
        f"📢 <b>В канал:</b> Только стикеры при редких семенах\n"
        f"🏓 <b>Самопинг:</b> Активен (каждые 8 минут)\n"
        f"💾 <b>Умный кэш:</b> Сохраняет состояние для каждого канала\n"
        f"🛡️ <b>Защита от спама:</b> Автоматические паузы между сообщениями\n"
        f"🧹 <b>Очистка памяти:</b> Автоматическая оптимизация\n"
        f"📊 <b>Авто-статус:</b> Каждые 5 часов\n\n"
        f"🎯 <b>Отслеживаю семена:</b>\n"
        f"{seeds_list_bot}\n\n"
        f"🎛️ <b>Команды:</b>\n"
        f"/start - Информация\n"
        f"/status - Статус\n" 
        f"/enable - Включить канал\n"
        f"/disable - Выключить канал\n"
        f"/help - Помощь"
    )
    
    send_to_bot(startup_msg_bot)
    
    app.run(host='0.0.0.0', port=5000)
