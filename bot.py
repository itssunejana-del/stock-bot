from flask import Flask, request
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
import re
import json

# ==================== ЭКСТРЕННАЯ ПАУЗА ====================
PAUSE_BOT = os.getenv('PAUSE_BOT', 'false').lower() == 'true'

if PAUSE_BOT:
    print("⏸️ БОТ ПРИОСТАНОВЛЕН НА 2 ЧАСА")
    print("Discord ограничил запросы. Ожидаю снятия ограничений...")
    time.sleep(7200)  # 2 часа
    print("⏰ 2 часа прошли, продолжаю...")
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
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# ID каналов Discord
SEEDS_CHANNEL_ID = os.getenv('SEEDS_CHANNEL_ID')
EGGS_CHANNEL_ID = os.getenv('EGGS_CHANNEL_ID')
PASS_SHOP_CHANNEL_ID = os.getenv('PASS_SHOP_CHANNEL_ID')

# Проверяем обязательные переменные
if not all([TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID, TELEGRAM_BOT_CHAT_ID, DISCORD_TOKEN]):
    logger.error("❌ Отсутствуют обязательные переменные окружения!")
if not all([SEEDS_CHANNEL_ID, EGGS_CHANNEL_ID, PASS_SHOP_CHANNEL_ID]):
    logger.error("❌ Не все ID каналов указаны!")

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

# ==================== РАСПИСАНИЕ ЗАПРОСОВ ====================
# Формат: {channel_id: [(минута, секунда), ...]}
SCHEDULES = {
    SEEDS_CHANNEL_ID: [  # Семена - 5 запросов за 3 минуты
        (0, 20),   # 00:20
        (0, 40),   # 00:40  
        (1, 0),    # 01:00
        (2, 0),    # 02:00
        (3, 0)     # 03:00
    ],
    EGGS_CHANNEL_ID: [  # Яйца - 6 запросов за 20 минут
        (0, 30),   # 00:30
        (1, 0),    # 01:00
        (2, 0),    # 02:00
        (5, 0),    # 05:00
        (10, 0),   # 10:00
        (20, 0)    # 20:00
    ],
    PASS_SHOP_CHANNEL_ID: [  # Пасс-шоп - 3 запроса за 2 минуты
        (0, 40),   # 00:40
        (1, 10),   # 01:10
        (1, 40)    # 01:40
    ]
}

# Названия каналов для логов
CHANNEL_NAMES = {
    SEEDS_CHANNEL_ID: "🌱 Семена",
    EGGS_CHANNEL_ID: "🥚 Яйца",
    PASS_SHOP_CHANNEL_ID: "🎫 Пасс-шоп"
}

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
last_processed_ids = {
    SEEDS_CHANNEL_ID: None,
    EGGS_CHANNEL_ID: None,
    PASS_SHOP_CHANNEL_ID: None
}
CACHE_FILE = 'last_processed_ids.json'
startup_time = datetime.now()
channel_enabled = True
bot_status = "🟢 Работает по расписанию"
last_error = None
processed_messages_cache = set()
telegram_offset = 0
ping_count = 0
last_ping_time = None
found_seeds_count = {name: 0 for name in TARGET_SEEDS.keys()}
sticker_sent_cache = {}  # Для предотвращения дублей стикеров

# ==================== СИСТЕМА СОХРАНЕНИЯ СОСТОЯНИЯ ====================
def save_last_processed_ids():
    """Сохраняет last_processed_ids в файл"""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(last_processed_ids, f)
        logger.info("💾 Сохранены last_processed_ids")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения: {e}")

def load_last_processed_ids():
    """Загружает last_processed_ids из файла"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                loaded_ids = json.load(f)
                # Обновляем только существующие каналы
                for channel_id in [SEEDS_CHANNEL_ID, EGGS_CHANNEL_ID, PASS_SHOP_CHANNEL_ID]:
                    if channel_id in loaded_ids:
                        last_processed_ids[channel_id] = loaded_ids[channel_id]
                logger.info("📂 Загружены last_processed_ids из файла")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")

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
            logger.info(f"📱 Отправлено в Telegram")
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram, жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Ошибка Telegram {response.status_code}")
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
            logger.info(f"📱 Отправлен стикер")
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram, жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Ошибка отправки стикера")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def send_to_channel(text=None, sticker_id=None):
    """Отправляет в Telegram канал с защитой от спама"""
    if not channel_enabled:
        return False
    
    if not hasattr(send_to_channel, 'last_message_time'):
        send_to_channel.last_message_time = 0
    
    current_time = time.time()
    if current_time - send_to_channel.last_message_time < 2:
        time.sleep(2 - (current_time - send_to_channel.last_message_time))
    
    send_to_channel.last_message_time = time.time()
    
    if sticker_id:
        return send_telegram_sticker(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    
    return False

def send_to_bot(text):
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

# ==================== DISCORD ФУНКЦИИ ====================
def fetch_discord_messages(channel_id, limit=5):
    """Получает сообщения из Discord канала"""
    if not DISCORD_TOKEN:
        logger.error("❌ Нет токена Discord")
        return None
    
    try:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            retry_after = response.json().get('retry_after', 1)
            logger.warning(f"⚠️ Лимит Discord, жду {retry_after} сек")
            time.sleep(retry_after)
            return None
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Discord: {e}")
        return None

def clean_text_for_display(text):
    """Очищает текст для Telegram"""
    text = re.sub(r'<:[a-zA-Z0-9_]+:(\d+)>', '', text)
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'<t:\d+:[tR]>', '', text)
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if line and ('x' in line or ':' in line or any(word in line.lower() for word in 
                   ['seeds', 'gear', 'alert', 'stock', 'egg', 'pass'])):
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def extract_all_text_from_message(message):
    """Извлекает весь текст из сообщения"""
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

def process_discord_message(message, channel_id):
    """Обрабатывает одно сообщение из Discord"""
    global found_seeds_count, bot_status, last_error, sticker_sent_cache
    
    try:
        message_id = message.get('id')
        author = message.get('author', {}).get('username', '')
        
        # Проверяем что это Kiro
        if 'kiro' not in author.lower():
            return False
        
        # Проверяем дубли
        if message_id in processed_messages_cache:
            return False
        
        processed_messages_cache.add(message_id)
        
        # Получаем весь текст
        all_text = extract_all_text_from_message(message)
        search_text = all_text.lower()
        
        # Проверяем на наличие отслеживаемых предметов
        found_items = []
        should_send_to_bot = False
        
        for seed_name, seed_config in TARGET_SEEDS.items():
            for keyword in seed_config['keywords']:
                if keyword in search_text:
                    found_seeds_count[seed_name] += 1
                    found_items.append(seed_config['display_name'])
                    
                    # Проверяем отправляли ли уже стикер для этого предмета в этом цикле
                    current_minute = datetime.now().minute
                    cycle_key = f"{seed_name}_{channel_id}_{current_minute // 5 if channel_id != EGGS_CHANNEL_ID else current_minute // 30}"
                    
                    if cycle_key not in sticker_sent_cache:
                        # Отправляем стикер в канал
                        sticker_sent = send_to_channel(sticker_id=seed_config['sticker_id'])
                        if sticker_sent:
                            logger.info(f"✅ Стикер {seed_config['emoji']} отправлен в канал")
                            send_to_bot(f"✅ Стикер {seed_config['emoji']} отправлен в канал")
                            sticker_sent_cache[cycle_key] = True
                        else:
                            logger.error(f"❌ Ошибка отправки стикера {seed_config['emoji']}")
                    
                    should_send_to_bot = True
                    break  # Прерываем после первого найденного ключевого слова
        
        # Если нашли отслеживаемые предметы, отправляем в бота
        if should_send_to_bot:
            cleaned_text = clean_text_for_display(all_text)
            if cleaned_text.strip():
                current_time = datetime.now().strftime('%H:%M:%S')
                channel_name = CHANNEL_NAMES.get(channel_id, "Неизвестный")
                
                bot_message = (
                    f"🎯 Найдены: {', '.join(found_items)}\n"
                    f"📡 Канал: {channel_name}\n"
                    f"⏰ Время: {current_time}\n\n"
                    f"<code>{cleaned_text[:1500]}</code>"
                )
                send_to_bot(bot_message)
        
        # Обновляем last_processed_id
        if (last_processed_ids[channel_id] is None or 
            int(message_id) > int(last_processed_ids[channel_id] or 0)):
            last_processed_ids[channel_id] = message_id
            save_last_processed_ids()
        
        bot_status = "🟢 Обработано новое сообщение"
        last_error = None
        
        return len(found_items) > 0
        
    except Exception as e:
        error_msg = f"Ошибка обработки сообщения: {e}"
        logger.error(f"💥 {error_msg}")
        bot_status = "🔴 Ошибка обработки"
        last_error = error_msg
        return False

def check_channel(channel_id):
    """Проверяет канал по расписанию"""
    if channel_id not in SCHEDULES:
        return False
    
    now = datetime.now()
    current_minute = now.minute
    current_second = now.second
    
    # Определяем цикл обновления
    if channel_id == EGGS_CHANNEL_ID:  # Яйца каждые 30 минут
        cycle_minute = current_minute % 30
    else:  # Семена и пасс-шоп каждые 5 минут
        cycle_minute = current_minute % 5
    
    # Проверяем все запланированные времена
    for schedule_minute, schedule_second in SCHEDULES[channel_id]:
        if (cycle_minute == schedule_minute and 
            abs(current_second - schedule_second) <= 2):  # ±2 секунды для точности
            return True
    
    return False

def monitor_channels():
    """Основной мониторинг по расписанию"""
    logger.info("🔄 Запускаю мониторинг по расписанию...")
    
    # Загружаем сохраненные ID
    load_last_processed_ids()
    
    # Ждем немного при старте
    time.sleep(10)
    
    while True:
        try:
            current_time = datetime.now().strftime('%H:%M:%S')
            
            # Проверяем каждый канал по расписанию
            for channel_id in [SEEDS_CHANNEL_ID, EGGS_CHANNEL_ID, PASS_SHOP_CHANNEL_ID]:
                if check_channel(channel_id):
                    channel_name = CHANNEL_NAMES.get(channel_id, "Неизвестный")
                    logger.info(f"⏰ {current_time} - Проверяю {channel_name}")
                    
                    messages = fetch_discord_messages(channel_id)
                    if messages:
                        # Обрабатываем только новые сообщения
                        for message in messages:
                            message_id = message.get('id')
                            last_id = last_processed_ids[channel_id]
                            
                            # Если это первый запуск или сообщение новее
                            if last_id is None or int(message_id) > int(last_id):
                                process_discord_message(message, channel_id)
            
            # Очищаем кэш стикеров каждые 5 минут
            if datetime.now().minute % 5 == 0 and datetime.now().second < 10:
                sticker_sent_cache.clear()
                logger.info("🧹 Очищен кэш отправленных стикеров")
            
            # Очищаем кэш сообщений если нужно
            if len(processed_messages_cache) > 1000:
                processed_messages_cache.clear()
                logger.info("🧹 Очищен кэш обработанных сообщений")
            
            time.sleep(1)  # Короткая пауза
            
        except Exception as e:
            logger.error(f"💥 Ошибка мониторинга: {e}")
            time.sleep(30)

# ==================== САМОПИНГ И TELEGRAM КОМАНДЫ ====================
def simple_self_pinger():
    global ping_count, last_ping_time
    logger.info("🏓 Запускаю самопинг...")
    time.sleep(30)
    
    while True:
        try:
            ping_count += 1
            last_ping_time = datetime.now()
            logger.info(f"🏓 Самопинг #{ping_count}")
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
        time.sleep(300)

def telegram_poller():
    global telegram_offset
    logger.info("🤖 Запускаю Telegram поллер...")
    time.sleep(10)
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {'offset': telegram_offset + 1, 'timeout': 10, 'limit': 1}
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
                            
                            if text.startswith('/'):
                                handle_telegram_command(chat_id, text)
            
            time.sleep(5)
        except Exception as e:
            logger.error(f"❌ Ошибка Telegram поллера: {e}")
            time.sleep(10)

def handle_telegram_command(chat_id, command):
    global channel_enabled
    
    if command == '/start':
        seeds_list = "\n".join([f"{config['emoji']} {config['display_name']}" 
                              for config in TARGET_SEEDS.values()])
        
        schedule_info = "\n".join([
            f"🌱 Семена: 5 запросов за 3 минуты (20с, 40с, 1м, 2м, 3м)",
            f"🥚 Яйца: 6 запросов за 20 минут (30с, 1м, 2м, 5м, 10м, 20м)",
            f"🎫 Пасс-шоп: 3 запроса за 2 минуты (40с, 1м10с, 1м40с)"
        ])
        
        welcome_text = (
            "🚀 <b>БОТ ЗАПУЩЕН С РАСПИСАНИЕМ!</b>\n\n"
            f"📡 <b>Расписание запросов:</b>\n{schedule_info}\n\n"
            f"🎯 <b>Отслеживаю:</b>\n{seeds_list}\n\n"
            "⚡ <b>Логика:</b>\n"
            "• Запросы только по расписанию\n"
            "• Стикер 1 раз на предмет за цикл\n"
            "• Только новые сообщения\n"
            "• Сохранение состояния\n\n"
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
        send_telegram_message(chat_id, "✅ <b>Канал ВКЛЮЧЕН</b>\nСтикеры будут отправляться.")
    
    elif command == '/disable':
        channel_enabled = False
        send_telegram_message(chat_id, "⏸️ <b>Канал ВЫКЛЮЧЕН</b>\nСтикеры приостановлены.")
    
    elif command == '/help':
        help_text = (
            "📋 <b>Команды:</b>\n"
            "/start - Информация\n"
            "/status - Статус\n"
            "/enable - Включить канал\n"
            "/disable - Выключить канал\n"
            "/help - Помощь"
        )
        send_telegram_message(chat_id, help_text)
    
    else:
        send_telegram_message(chat_id, "❌ Неизвестная команда. /help")

def send_bot_status(chat_id):
    global bot_status, last_error, channel_enabled, ping_count, last_ping_time, found_seeds_count
    
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    last_ping_str = "Еще не было" if not last_ping_time else last_ping_time.strftime('%H:%M:%S')
    
    seeds_stats = "\n".join([f"{config['emoji']} {config['display_name']}: {found_seeds_count.get(name, 0)} раз" 
                           for name, config in TARGET_SEEDS.items()])
    
    current_time = datetime.now()
    
    # Информация о следующем запросе
    next_checks = []
    for channel_id, channel_name in CHANNEL_NAMES.items():
        if channel_id in SCHEDULES:
            next_time = get_next_check_time(channel_id, current_time)
            next_checks.append(f"{channel_name}: {next_time}")
    
    status_text = (
        f"📊 <b>Статус бота (Расписание)</b>\n\n"
        f"{bot_status}\n"
        f"⏰ Работает: {hours:.1f} часов\n"
        f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"📡 Каналов: 3\n"
        f"🏓 Самопинг: {ping_count} раз\n"
        f"💾 Кэш: {len(processed_messages_cache)} сообщений\n\n"
        f"⏰ <b>Текущее время:</b> {current_time.strftime('%H:%M:%S')}\n\n"
        f"🎯 <b>Найдено:</b>\n{seeds_stats}"
    )
    
    if next_checks:
        status_text += f"\n\n🔄 <b>Следующие проверки:</b>\n" + "\n".join(next_checks)
    
    if last_error:
        status_text += f"\n\n⚠️ <b>Последняя ошибка:</b>\n<code>{last_error}</code>"
    
    send_telegram_message(chat_id, status_text)

def get_next_check_time(channel_id, current_time):
    """Возвращает время следующей проверки"""
    if channel_id not in SCHEDULES:
        return "Неизвестно"
    
    current_minute = current_time.minute
    current_second = current_time.second
    
    if channel_id == EGGS_CHANNEL_ID:
        cycle_minute = current_minute % 30
        cycle_start = current_time - timedelta(minutes=cycle_minute, seconds=current_second)
    else:
        cycle_minute = current_minute % 5
        cycle_start = current_time - timedelta(minutes=cycle_minute, seconds=current_second)
    
    # Ищем следующее запланированное время
    for schedule_minute, schedule_second in SCHEDULES[channel_id]:
        if (cycle_minute < schedule_minute) or (cycle_minute == schedule_minute and current_second < schedule_second):
            next_time = cycle_start + timedelta(minutes=schedule_minute, seconds=schedule_second)
            return next_time.strftime('%H:%M:%S')
    
    # Если все проверки прошли, следующая в следующем цикле
    if channel_id == EGGS_CHANNEL_ID:
        next_cycle = cycle_start + timedelta(minutes=30)
    else:
        next_cycle = cycle_start + timedelta(minutes=5)
    
    first_check_minute, first_check_second = SCHEDULES[channel_id][0]
    next_time = next_cycle + timedelta(minutes=first_check_minute, seconds=first_check_second)
    return next_time.strftime('%H:%M:%S')

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    seeds_list = ", ".join([f"{config['emoji']} {config['display_name']}" 
                          for config in TARGET_SEEDS.values()])
    
    current_time = datetime.now().strftime('%H:%M:%S')
    
    return f"""
    <html>
        <head>
            <title>🌱 Seed Monitor (Расписание)</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                .status {{ background: #f0f8f0; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .schedule {{ background: #e3f2fd; padding: 20px; margin: 10px 0; border-radius: 8px; }}
                .seeds {{ background: #f3e5f5; padding: 20px; margin: 10px 0; border-radius: 8px; }}
                .button {{ background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 5px; display: inline-block; }}
            </style>
        </head>
        <body>
            <h1>🌱 Мониторинг семян (Расписание)</h1>
            
            <div class="status">
                <h3>📊 Статус</h3>
                <p><strong>Состояние:</strong> {bot_status}</p>
                <p><strong>Время работы:</strong> {hours:.1f} часов</p>
                <p><strong>Текущее время:</strong> {current_time}</p>
                <p><strong>Канал:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</p>
            </div>
            
            <div class="schedule">
                <h3>🕐 Расписание запросов</h3>
                <p><strong>🌱 Семена:</strong> 20с, 40с, 1м, 2м, 3м после обновления</p>
                <p><strong>🥚 Яйца:</strong> 30с, 1м, 2м, 5м, 10м, 20м после обновления</p>
                <p><strong>🎫 Пасс-шоп:</strong> 40с, 1м10с, 1м40с после обновления</p>
            </div>
            
            <div class="seeds">
                <h3>🎯 Отслеживаемые предметы</h3>
                <p>{seeds_list}</p>
            </div>
            
            <div>
                <a href="/enable_channel" class="button">✅ Включить канал</a>
                <a href="/disable_channel" class="button" style="background: #f44336;">⏸️ Выключить канал</a>
            </div>
        </body>
    </html>
    """

@app.route('/enable_channel')
def enable_channel_route():
    global channel_enabled
    channel_enabled = True
    return "✅ Канал включен"

@app.route('/disable_channel')
def disable_channel_route():
    global channel_enabled
    channel_enabled = False
    return "⏸️ Канал выключен"

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    # Логируем информацию о расписании
    logger.info("🚀 Запуск бота с расписанием")
    logger.info("📡 Расписание запросов:")
    for channel_id, schedule in SCHEDULES.items():
        channel_name = CHANNEL_NAMES.get(channel_id, "Неизвестный")
        times = [f"{m}м{s}с" for m, s in schedule]
        logger.info(f"  {channel_name}: {', '.join(times)} после обновления")
    
    logger.info(f"🎯 Отслеживаю {len(TARGET_SEEDS)} предметов")
    
    # Запускаем потоки
    threads = [
        threading.Thread(target=monitor_channels, daemon=True, name="Monitor"),
        threading.Thread(target=telegram_poller, daemon=True, name="TelegramPoller"),
        threading.Thread(target=simple_self_pinger, daemon=True, name="SelfPinger")
    ]
    
    for thread in threads:
        thread.start()
        time.sleep(1)
        logger.info(f"✅ Запущен поток: {thread.name}")
    
    # Стартовое сообщение
    try:
        startup_msg = (
            "🚀 <b>БОТ ЗАПУЩЕН С РАСПИСАНИЕМ!</b>\n\n"
            "📡 <b>Расписание запросов:</b>\n"
            "🌱 Семена: 20с, 40с, 1м, 2м, 3м после обновления\n"
            "🥚 Яйца: 30с, 1м, 2м, 5м, 10м, 20м после обновления\n"
            "🎫 Пасс-шоп: 40с, 1м10с, 1м40с после обновления\n\n"
            "✅ <b>Готов к работе!</b>\n"
            "Отправьте /status для проверки."
        )
        send_to_bot(startup_msg)
    except Exception as e:
        logger.error(f"❌ Не удалось отправить стартовое сообщение: {e}")
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
