from flask import Flask, request, jsonify
import requests
import os
import time
import logging
import threading
from datetime import datetime
import re
import json

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
SEEDS_CHANNEL_ID = os.getenv('SEEDS_CHANNEL_ID')
EGGS_CHANNEL_ID = os.getenv('EGGS_CHANNEL_ID')
PASS_SHOP_CHANNEL_ID = os.getenv('PASS_SHOP_CHANNEL_ID')

# Проверка переменных
REQUIRED_VARS = ['TELEGRAM_TOKEN', 'TELEGRAM_CHANNEL_ID', 'TELEGRAM_BOT_CHAT_ID', 
                 'DISCORD_TOKEN', 'SEEDS_CHANNEL_ID', 'EGGS_CHANNEL_ID', 'PASS_SHOP_CHANNEL_ID']
missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
if missing:
    logger.error(f"❌ Отсутствуют переменные: {missing}")

# ==================== ОТСЛЕЖИВАЕМЫЕ ПРЕДМЕТЫ ====================
TARGET_ITEMS = {
    'tomato': {
        'keywords': ['tomato', 'томат', ':tomato'],
        'sticker_id': "CAACAgIAAxkBAAEP-3lpOtdl3thyaZN8BfxTSAvD6kEkKgACf3sAAoEeWUgkKobs-st7ojYE",
        'emoji': '🍅',
        'display_name': 'Tomato',
        'channels': [SEEDS_CHANNEL_ID]
    },
    'octobloom': {
        'keywords': ['octobloom', 'октоблум', ':octobloom'],
        'sticker_id': "CAACAgIAAxkBAAEP1btpIXhIEvgVEK4c6ugJv1EgP7UY-wAChokAAtZpCElVMcRUgb_jdDYE",
        'emoji': '🐙',
        'display_name': 'Octobloom',
        'channels': [SEEDS_CHANNEL_ID]
    },
    'zebrazinkle': {
        'keywords': ['zebrazinkle', 'zebra zinkle', ':zebrazinkle'],
        'sticker_id': "CAACAgIAAxkBAAEPwjJpFDhW_6Vu29vF7DrTHFBcSf_WIAAC1XkAAkCXoUgr50G4SlzwrzYE",
        'emoji': '🦓',
        'display_name': 'Zebrazinkle',
        'channels': [SEEDS_CHANNEL_ID]
    },
    'peppermint_vine': {
        'keywords': ['peppermint vine', 'peppermintvine', ':peppermintvine'],
        'sticker_id': "CAACAgIAAxkBAAEP9hZpNtYLGgXJ5UmFIzEjQ6tL6jX-_QACrokAAk1ouUn1z9iCPYIanzYE",
        'emoji': '🌿',
        'display_name': 'Peppermint Vine',
        'channels': [SEEDS_CHANNEL_ID]
    },
    'gem_egg': {
        'keywords': ['gem egg', 'gemegg', ':gemegg'],
        'sticker_id': "CAACAgIAAxkBAAEP1b9pIXhSl-ElpsKgOEEY-8oOmJ1qnAACI4MAAq6w2EinW-vu8EV_RzYE",
        'emoji': '💎',
        'display_name': 'Gem Egg',
        'channels': [EGGS_CHANNEL_ID]
    },
    'pollen_cone': {
        'keywords': ['pollen cone', 'pollencone', ':pollencone'],
        'sticker_id': "CAACAgIAAxkBAAEP-4hpOtmoKIOXpzx89yFx3StQK77KzQACQI8AAuZU2Emfi_MTLWoHDjYE",
        'emoji': '🍯',
        'display_name': 'Pollen Cone',
        'channels': [PASS_SHOP_CHANNEL_ID]
    }
}

CHANNEL_NAMES = {
    SEEDS_CHANNEL_ID: '🌱 Семена',
    EGGS_CHANNEL_ID: '🥚 Яйца',
    PASS_SHOP_CHANNEL_ID: '🎫 Пасс-шоп'
}

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
last_processed_ids = {
    SEEDS_CHANNEL_ID: None,
    EGGS_CHANNEL_ID: None,
    PASS_SHOP_CHANNEL_ID: None
}
processed_messages_cache = set()
bot_start_time = datetime.now()
bot_status = "🟢 Инициализация"
channel_enabled = True
found_items_count = {name: 0 for name in TARGET_ITEMS.keys()}
discord_request_count = 0
last_discord_request = 0
cycle_active_flags = {}  # Флаги активных циклов для каждого канала
found_in_current_cycle = {}  # Найденные предметы в текущем цикле

STATE_FILE = 'bot_state.json'

# ==================== УМНОЕ РАСПИСАНИЕ ====================
CHANNEL_SCHEDULES = {
    SEEDS_CHANNEL_ID: [  # 🌱 Семена: 3 проверки за 5-минутный цикл
        (0, 20),  # 20 сек
        (0, 40),  # 40 сек
        (1, 0)    # 1 мин
    ],
    EGGS_CHANNEL_ID: [    # 🥚 Яйца: 5 проверок за 30-минутный цикл
        (0, 30),  # 30 сек
        (1, 0),   # 1 мин
        (2, 0),   # 2 мин
        (5, 0),   # 5 мин
        (10, 0)   # 10 мин
    ],
    PASS_SHOP_CHANNEL_ID: [  # 🎫 Пасс-шоп: 2 проверки за 5-минутный цикл
        (0, 40),   # 40 сек
        (1, 10)    # 1 мин 10 сек
    ]
}

CHANNEL_CYCLE_LENGTHS = {
    SEEDS_CHANNEL_ID: 5,     # 5 минут
    EGGS_CHANNEL_ID: 30,     # 30 минут
    PASS_SHOP_CHANNEL_ID: 5  # 5 минут
}

# ==================== СИСТЕМА СОХРАНЕНИЯ СОСТОЯНИЯ ====================
def save_bot_state():
    try:
        state = {
            'last_processed_ids': last_processed_ids,
            'found_items_count': found_items_count,
            'saved_at': datetime.now().isoformat()
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        logger.debug("💾 Состояние сохранено")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения состояния: {e}")

def load_bot_state():
    global last_processed_ids, found_items_count
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                for channel_id in [SEEDS_CHANNEL_ID, EGGS_CHANNEL_ID, PASS_SHOP_CHANNEL_ID]:
                    if channel_id in state.get('last_processed_ids', {}):
                        last_processed_ids[channel_id] = state['last_processed_ids'][channel_id]
                
                loaded_counts = state.get('found_items_count', {})
                for item_name, count in loaded_counts.items():
                    if item_name in found_items_count:
                        found_items_count[item_name] = count
                
                logger.info("📂 Состояние загружено")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки состояния: {e}")

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML", disable_notification=False):
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification
        }
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram, жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Ошибка Telegram {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def send_telegram_sticker(chat_id, sticker_id, disable_notification=True):
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {
            "chat_id": chat_id,
            "sticker": sticker_id,
            "disable_notification": disable_notification
        }
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram (стикер), жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Ошибка отправки стикера {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки стикера: {e}")
        return False

def send_to_channel(sticker_id=None, text=None):
    if not channel_enabled or not TELEGRAM_CHANNEL_ID:
        return False
    
    if not hasattr(send_to_channel, 'last_send_time'):
        send_to_channel.last_send_time = 0
    
    current_time = time.time()
    time_since_last = current_time - send_to_channel.last_send_time
    if time_since_last < 2:
        time.sleep(2 - time_since_last)
    
    send_to_channel.last_send_time = time.time()
    
    if sticker_id:
        return send_telegram_sticker(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    return False

def send_to_bot(text, disable_notification=False):
    if not TELEGRAM_BOT_CHAT_ID:
        return False
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text, disable_notification=disable_notification)

# ==================== DISCORD API ====================
def fetch_discord_messages(channel_id, limit=2):
    global discord_request_count, last_discord_request
    
    if not DISCORD_TOKEN or not channel_id:
        return None
    
    # Защита: 1 запрос в 5 секунд
    current_time = time.time()
    time_since_last = current_time - last_discord_request
    if time_since_last < 5:
        time.sleep(5 - time_since_last)
    
    discord_request_count += 1
    last_discord_request = time.time()
    
    try:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            if not response.text or response.text.strip() == '':
                return None
            
            try:
                messages = response.json()
            except json.JSONDecodeError:
                logger.error(f"❌ Ошибка JSON от Discord")
                return None
            
            # Фильтруем только Kiro
            kiro_messages = []
            for msg in messages:
                author = msg.get('author', {})
                username = author.get('username', '').lower()
                is_bot = author.get('bot', False)
                if ('kiro' in username) or (is_bot and 'kiro' in username):
                    kiro_messages.append(msg)
            
            return kiro_messages
                
        elif response.status_code == 429:
            retry_after = response.json().get('retry_after', 5.0)
            logger.warning(f"⏳ Discord API лимит. Жду {retry_after} сек.")
            time.sleep(retry_after)
            return None
        else:
            logger.error(f"❌ Ошибка Discord API {response.status_code}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("⏰ Таймаут запроса к Discord")
        return None
    except Exception as e:
        logger.error(f"❌ Неизвестная ошибка Discord: {e}")
        return None

def extract_text_from_message(message):
    full_text = message.get('content', '').lower()
    
    for embed in message.get('embeds', []):
        if embed.get('title'):
            full_text += ' ' + embed.get('title', '').lower()
        if embed.get('description'):
            full_text += ' ' + embed.get('description', '').lower()
        for field in embed.get('fields', []):
            full_text += ' ' + field.get('name', '').lower()
            full_text += ' ' + field.get('value', '').lower()
    
    return full_text

# ==================== УМНОЕ РАСПИСАНИЕ С ПРЕРЫВАНИЕМ ====================
def should_check_channel_now(channel_id):
    """Определяет, нужно ли проверять канал прямо сейчас по расписанию"""
    now = datetime.now()
    minute = now.minute
    second = now.second
    
    cycle_length = CHANNEL_CYCLE_LENGTHS.get(channel_id, 5)
    minute_in_cycle = minute % cycle_length
    
    # Если цикл уже был прерван - не проверяем
    if channel_id in cycle_active_flags and not cycle_active_flags[channel_id]:
        return False
    
    schedule = CHANNEL_SCHEDULES.get(channel_id, [])
    for check_minute, check_second in schedule:
        if minute_in_cycle == check_minute and second == check_second:
            return True
    
    return False

def process_discord_messages(channel_id, check_number):
    """Обрабатывает сообщения и возвращает (нашли_kiro, нашли_предметы)"""
    global last_processed_ids, found_items_count, bot_status, cycle_active_flags
    
    channel_name = CHANNEL_NAMES.get(channel_id, channel_id)
    
    # Получаем сообщения
    messages = fetch_discord_messages(channel_id, limit=2)
    if not messages:
        logger.info(f"📭 Проверка #{check_number}: В {channel_name} нет сообщений от Kiro")
        return (False, False)  # Не нашли Kiro, продолжаем цикл
    
    found_kiro = False
    found_items = False
    
    for message in messages:
        message_id = message['id']
        
        # Пропускаем если уже обрабатывали
        if message_id in processed_messages_cache:
            continue
        
        # Пропускаем если сообщение старше последнего обработанного
        last_id = last_processed_ids.get(channel_id)
        if last_id and int(message_id) <= int(last_id):
            continue
        
        # Нашли новое сообщение от Kiro!
        found_kiro = True
        processed_messages_cache.add(message_id)
        
        # Ограничиваем размер кэша
        if len(processed_messages_cache) > 100:
            oldest = list(processed_messages_cache)[:50]
            for msg_id in oldest:
                processed_messages_cache.remove(msg_id)
        
        # Извлекаем текст
        text = extract_text_from_message(message)
        
        # Ищем целевые предметы
        found_items_in_message = []
        
        for item_name, item_config in TARGET_ITEMS.items():
            if channel_id not in item_config['channels']:
                continue
            
            for keyword in item_config['keywords']:
                if keyword.lower() in text:
                    # Проверяем, не находили ли уже в этом цикле
                    cycle_key = f"{channel_id}_{datetime.now().strftime('%H%M')[:4]}"
                    item_key = f"{cycle_key}_{item_name}"
                    
                    if item_key not in found_in_current_cycle:
                        found_items_count[item_name] += 1
                        found_items_in_message.append(item_config)
                        found_in_current_cycle[item_key] = True
                        logger.info(f"🎯 Найден {item_config['emoji']} {item_config['display_name']} в {channel_name}!")
                    break
        
        # Обрабатываем найденные предметы
        if found_items_in_message:
            found_items = True
            
            for item in found_items_in_message:
                if send_to_channel(sticker_id=item['sticker_id']):
                    current_time_str = datetime.now().strftime('%H:%M:%S')
                    notification = f"✅ Найден {item['emoji']} {item['display_name']} в {current_time_str}"
                    send_to_bot(notification, disable_notification=False)
                    logger.info(f"✅ Стикер {item['emoji']} отправлен в канал")
                else:
                    logger.error(f"❌ Ошибка отправки стикера {item['emoji']}")
        
        # Обновляем последний обработанный ID
        last_processed_ids[channel_id] = message_id
    
    # Сохраняем состояние если нашли предметы
    if found_items:
        save_bot_state()
    
    bot_status = f"🟢 Проверен {channel_name}"
    return (found_kiro, found_items)

# ==================== ГЛАВНЫЙ МОНИТОР ====================
def schedule_monitor():
    """Основной монитор с умным прерыванием циклов"""
    logger.info("👁️‍🗨️ Запуск умного мониторинга с прерыванием циклов...")
    load_bot_state()
    
    # Инициализируем флаги активных циклов
    for channel_id in [SEEDS_CHANNEL_ID, EGGS_CHANNEL_ID, PASS_SHOP_CHANNEL_ID]:
        cycle_active_flags[channel_id] = True
    
    # Отправляем стартовое сообщение
    startup_msg = (
        "🚀 <b>УМНЫЙ мониторинг Kiro запущен</b>\n\n"
        "🎯 <b>Логика с прерыванием циклов:</b>\n"
        "• Нашли Kiro → прекращаем проверки в этом цикле\n"
        "• Нашли предметы → отправляем стикер\n"
        "• Не нашли Kiro → продолжаем по расписанию\n\n"
        "🔄 <b>Расписание проверок:</b>\n"
        "• 🌱 Семена: 20с, 40с, 1м (3 проверки)\n"
        "• 🥚 Яйца: 30с, 1м, 2м, 5м, 10м (5 проверок)\n"
        "• 🎫 Пасс-шоп: 40с, 1м10с (2 проверки)\n\n"
        "✅ <b>Готов к работе!</b>"
    )
    send_to_bot(startup_msg)
    
    # Счетчики проверок для каждого канала
    check_counters = {
        SEEDS_CHANNEL_ID: 0,
        EGGS_CHANNEL_ID: 0,
        PASS_SHOP_CHANNEL_ID: 0
    }
    
    while True:
        try:
            now = datetime.now()
            current_minute = now.minute
            
            # Проверяем каждый канал
            for channel_id in [SEEDS_CHANNEL_ID, EGGS_CHANNEL_ID, PASS_SHOP_CHANNEL_ID]:
                channel_name = CHANNEL_NAMES.get(channel_id, channel_id)
                
                # Проверяем, не начался ли новый цикл
                cycle_length = CHANNEL_CYCLE_LENGTHS.get(channel_id, 5)
                if current_minute % cycle_length == 0:
                    # Новый цикл! Сбрасываем флаг
                    cycle_active_flags[channel_id] = True
                    check_counters[channel_id] = 0
                    logger.debug(f"🔄 Начался новый цикл для {channel_name}")
                
                # Проверяем по расписанию
                if should_check_channel_now(channel_id) and cycle_active_flags.get(channel_id, True):
                    check_counters[channel_id] += 1
                    logger.info(f"🕐 Проверка #{check_counters[channel_id]} для {channel_name}...")
                    
                    found_kiro, found_items = process_discord_messages(channel_id, check_counters[channel_id])
                    
                    if found_kiro:
                        # Нашли Kiro - прерываем цикл
                        cycle_active_flags[channel_id] = False
                        if found_items:
                            logger.info(f"✅ Найдены предметы в {channel_name} - цикл прерван")
                        else:
                            logger.info(f"📭 Найден Kiro без предметов в {channel_name} - цикл прерван")
                    else:
                        logger.info(f"📭 Не нашли Kiro в {channel_name} - продолжаем цикл")
                    
                    # Пауза между запросами
                    time.sleep(2)
            
            # Очистка кэша найденных предметов (каждые 10 минут)
            if now.minute % 10 == 0 and now.second < 5:
                old_size = len(found_in_current_cycle)
                if old_size > 50:
                    # Оставляем только последние 20 записей
                    keys = list(found_in_current_cycle.keys())
                    for key in keys[:-20]:
                        del found_in_current_cycle[key]
                    logger.debug(f"🧹 Очищен кэш предметов: {old_size} -> {len(found_in_current_cycle)}")
            
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторе: {e}")
            time.sleep(10)

def status_monitor():
    """Отправляет статус каждые 6 часов"""
    logger.info("📊 Монитор статуса запущен (каждые 6 часов)")
    time.sleep(60)
    
    while True:
        try:
            time.sleep(6 * 60 * 60)
            
            uptime = datetime.now() - bot_start_time
            uptime_hours = uptime.total_seconds() / 3600
            
            items_stats = []
            for item_name, count in found_items_count.items():
                if count > 0:
                    item = TARGET_ITEMS[item_name]
                    items_stats.append(f"{item['emoji']} {item['display_name']}: {count}")
            
            stats_text = "\n".join(items_stats) if items_stats else "Еще не найдено"
            
            channels_status = []
            for channel_id, channel_name in CHANNEL_NAMES.items():
                last_id = last_processed_ids.get(channel_id, 'Не обработано')
                active = "🟢" if cycle_active_flags.get(channel_id, True) else "⏸️"
                channels_status.append(f"{channel_name}: {last_id} {active}")
            
            status_msg = (
                f"📊 <b>Авто-статус бота (6ч)</b>\n\n"
                f"⏰ Время работы: {uptime_hours:.1f} часов\n"
                f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
                f"🔄 Запросов к Discord: {discord_request_count}\n"
                f"📡 Циклы: {'/'.join(['🟢' if v else '⏸️' for v in cycle_active_flags.values()])}\n\n"
                f"🎯 <b>Найдено предметов:</b>\n{stats_text}\n\n"
                f"📝 <b>Состояние каналов:</b>\n" + "\n".join(channels_status)
            )
            
            send_to_bot(status_msg)
            logger.info("📊 Отправлен авто-статус")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки статуса: {e}")

def self_pinger():
    """Самопинг"""
    logger.info("🏓 Самопинг запущен (каждые 8 минут)")
    time.sleep(30)
    
    while True:
        try:
            logger.info("🏓 Самопинг: сервис активен")
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
        
        time.sleep(8 * 60)

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    uptime = datetime.now() - bot_start_time
    uptime_str = str(uptime).split('.')[0]
    
    found_items = []
    for item_name, count in found_items_count.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            found_items.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    cycles_status = []
    for channel_id, channel_name in CHANNEL_NAMES.items():
        active = "🟢 Активен" if cycle_active_flags.get(channel_id, True) else "⏸️ Прерван"
        cycles_status.append(f"{channel_name}: {active}")
    
    return f"""
    <html>
    <head>
        <title>🌱 Умный мониторинг Kiro</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .card {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .status-ok {{ color: #2ecc71; }}
            .status-paused {{ color: #f39c12; }}
            .button {{ 
                display: inline-block; 
                padding: 10px 20px; 
                margin: 5px; 
                background: #3498db; 
                color: white; 
                text-decoration: none; 
                border-radius: 5px;
            }}
        </style>
    </head>
    <body>
        <h1>🌱 Умный мониторинг Kiro</h1>
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> <span class="status-ok">{bot_status}</span></p>
            <p><strong>Время работы:</strong> {uptime_str}</p>
            <p><strong>Telegram-канал:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</p>
            <p><strong>Запросов к Discord:</strong> {discord_request_count}</p>
            <p><strong>В кэше сообщений:</strong> {len(processed_messages_cache)}</p>
        </div>
        
        <div class="card">
            <h2>🔄 Состояние циклов</h2>
            <ul>{"".join([f'<li>{status}</li>' for status in cycles_status])}</ul>
        </div>
        
        <div class="card">
            <h2>🎯 Управление</h2>
            <a href="/enable" class="button">✅ Включить канал</a>
            <a href="/disable" class="button">⏸️ Выключить канал</a>
            <a href="/status" class="button">📊 Статус</a>
            <a href="/health" class="button">❤️ Здоровье</a>
        </div>
        
        <div class="card">
            <h2>📡 Расписание проверок</h2>
            <ul>
                <li><strong>🌱 Семена (5 мин цикл):</strong> 20с, 40с, 1м (3 проверки)</li>
                <li><strong>🥚 Яйца (30 мин цикл):</strong> 30с, 1м, 2м, 5м, 10м (5 проверок)</li>
                <li><strong>🎫 Пасс-шоп (5 мин цикл):</strong> 40с, 1м10с (2 проверки)</li>
            </ul>
        </div>
        
        <div class="card">
            <h2>🏆 Найдено предметов</h2>
            <ul>{"".join([f'<li>{item}</li>' for item in found_items]) if found_items else '<li>Еще не найдено</li>'}</ul>
        </div>
        
        <div class="card">
            <h2>🧠 Логика работы</h2>
            <p><strong>✅ Нашли сообщение от Kiro → прекращаем проверки в этом цикле</strong></p>
            <p><strong>✅ Нашли отслеживаемые предметы → отправляем стикер в канал</strong></p>
            <p><strong>✅ Не нашли Kiro → продолжаем по расписанию</strong></p>
            <p><strong>🛡️ Защита от дублей: запоминаем найденное в цикле</strong></p>
        </div>
    </body>
    </html>
    """

@app.route('/enable')
def enable_channel():
    global channel_enabled
    channel_enabled = True
    send_to_bot("✅ <b>Отправка стикеров в канал ВКЛЮЧЕНА</b>")
    return "✅ Отправка стикеров в канал включена"

@app.route('/disable')
def disable_channel():
    global channel_enabled
    channel_enabled = False
    send_to_bot("⏸️ <b>Отправка стикеров в канал ВЫКЛЮЧЕНА</b>")
    return "⏸️ Отправка стикеров в канал выключена"

@app.route('/status')
def status_page():
    uptime = datetime.now() - bot_start_time
    uptime_hours = uptime.total_seconds() / 3600
    
    items_stats = []
    for item_name, count in found_items_count.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            items_stats.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    stats_text = "\n".join(items_stats) if items_stats else "Еще не найдено"
    
    channels_info = []
    for channel_id, channel_name in CHANNEL_NAMES.items():
        last_id = last_processed_ids.get(channel_id, 'Не обработано')
        active = "🟢 Активен" if cycle_active_flags.get(channel_id, True) else "⏸️ Прерван"
        channels_info.append(f"{channel_name}: {last_id} ({active})")
    
    return f"""
    <html>
    <head><title>Статус бота</title><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; margin: 40px;">
        <h1>📊 Статус бота</h1>
        <div class="card" style="background: #f5f5f5; padding: 20px; border-radius: 10px;">
            <p><strong>Время работы:</strong> {uptime_hours:.1f} часов</p>
            <p><strong>Состояние:</strong> {bot_status}</p>
            <p><strong>Канал:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</p>
            <p><strong>Запросов к Discord:</strong> {discord_request_count}</p>
            <p><strong>Найдено предметов:</strong></p>
            <pre>{stats_text}</pre>
            <p><strong>Состояние каналов:</strong></p>
            <pre>{"\\n".join(channels_info)}</pre>
            <p><a href="/">← Назад</a></p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': (datetime.now() - bot_start_time).total_seconds(),
        'discord_requests': discord_request_count,
        'channel_enabled': channel_enabled,
        'active_cycles': sum(1 for v in cycle_active_flags.values() if v),
        'found_items_total': sum(found_items_count.values())
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК УМНОГО МОНИТОРИНГА С ПРЕРЫВАНИЕМ ЦИКЛОВ")
    logger.info("=" * 60)
    logger.info("🎯 Логика: Нашли Kiro → прекращаем цикл")
    logger.info("📅 Расписание:")
    logger.info("  🌱 Семена: 20с, 40с, 1м (3 проверки)")
    logger.info("  🥚 Яйца: 30с, 1м, 2м, 5м, 10м (5 проверок)")
    logger.info("  🎫 Пасс-шоп: 40с, 1м10с (2 проверки)")
    logger.info("🛡️ Защита Discord: 1 запрос/5 секунд")
    logger.info("💾 Сохранение состояния: ВКЛЮЧЕНО")
    logger.info("=" * 60)
    
    threads = [
        threading.Thread(target=schedule_monitor, name='ScheduleMonitor', daemon=True),
        threading.Thread(target=status_monitor, name='StatusMonitor', daemon=True),
        threading.Thread(target=self_pinger, name='SelfPinger', daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Запущен поток: {thread.name}")
        time.sleep(1)
    
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
