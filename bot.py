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

# Проверка переменных окружения
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

# Названия каналов для логов
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
last_check_times = {}  # Для отслеживания времени последней проверки

# Файлы для сохранения состояния
STATE_FILE = 'bot_state.json'

# ==================== СИСТЕМА СОХРАНЕНИЯ СОСТОЯНИЯ ====================
def save_bot_state():
    """Сохраняет состояние бота в файл"""
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
    """Загружает состояние бота из файла"""
    global last_processed_ids, found_items_count
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                # Обновляем только существующие каналы
                for channel_id in [SEEDS_CHANNEL_ID, EGGS_CHANNEL_ID, PASS_SHOP_CHANNEL_ID]:
                    if channel_id in state.get('last_processed_ids', {}):
                        last_processed_ids[channel_id] = state['last_processed_ids'][channel_id]
                
                # Обновляем счетчики найденных предметов
                loaded_counts = state.get('found_items_count', {})
                for item_name, count in loaded_counts.items():
                    if item_name in found_items_count:
                        found_items_count[item_name] = count
                
                logger.info("📂 Состояние загружено из файла")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки состояния: {e}")

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML", disable_notification=False):
    """Отправляет сообщение в Telegram"""
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
            logger.debug(f"📨 Сообщение отправлено в Telegram")
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
    """Отправляет стикер в Telegram"""
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
    """Отправляет стикер или сообщение в Telegram-канал"""
    if not channel_enabled or not TELEGRAM_CHANNEL_ID:
        return False
    
    # Защита от слишком частых сообщений
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
    """Отправляет сообщение в личку бота - ТОЛЬКО важные уведомления"""
    if not TELEGRAM_BOT_CHAT_ID:
        return False
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text, disable_notification=disable_notification)

# ==================== DISCORD API С УЛУЧШЕННОЙ ЗАЩИТОЙ ====================
def fetch_discord_messages(channel_id, limit=2):  # Уменьшил с 3 до 2
    """Безопасно получает сообщения из Discord с защитой от лимитов"""
    global discord_request_count, last_discord_request
    
    if not DISCORD_TOKEN or not channel_id:
        return None
    
    # УВЕЛИЧЕННАЯ ЗАЩИТА: не чаще 1 запроса в 10 секунд
    current_time = time.time()
    time_since_last = current_time - last_discord_request
    if time_since_last < 10:  # Было 2, стало 10 секунд
        sleep_time = 10 - time_since_last
        logger.debug(f"⏸️ Защита от лимитов Discord: жду {sleep_time:.1f} сек")
        time.sleep(sleep_time)
    
    discord_request_count += 1
    last_discord_request = time.time()
    
    try:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            # ПРОВЕРКА НА ПУСТОЙ ОТВЕТ
            if not response.text or response.text.strip() == '':
                logger.warning("⚠️ Discord вернул пустой ответ")
                return None
            
            try:
                messages = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"❌ Ошибка декодирования JSON: {e}. Ответ: {response.text[:100]}")
                return None
            
            # Фильтруем только сообщения от Kiro
            kiro_messages = []
            for msg in messages:
                author = msg.get('author', {})
                username = author.get('username', '').lower()
                is_bot = author.get('bot', False)
                if ('kiro' in username) or (is_bot and 'kiro' in username):
                    kiro_messages.append(msg)
            
            if kiro_messages:
                logger.debug(f"📨 Получено {len(kiro_messages)} сообщений от Kiro")
            return kiro_messages
                
        elif response.status_code == 429:
            error_data = response.json()
            retry_after = error_data.get('retry_after', 5.0)  # Увеличил дефолт
            logger.warning(f"⏳ Discord API лимит. Жду {retry_after} сек.")
            time.sleep(retry_after)
            return None
        else:
            logger.error(f"❌ Ошибка Discord API {response.status_code}: {response.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("⏰ Таймаут запроса к Discord")
        return None
    except Exception as e:
        logger.error(f"❌ Неизвестная ошибка Discord: {e}")
        return None

def extract_text_from_message(message):
    """Извлекает весь текст из сообщения"""
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

# ==================== ОСНОВНАЯ ЛОГИКА ====================
def process_discord_messages(channel_id):
    """Обрабатывает сообщения из конкретного канала - ИСПРАВЛЕННАЯ"""
    global last_processed_ids, found_items_count, bot_status
    
    channel_name = CHANNEL_NAMES.get(channel_id, channel_id)
    
    # Получаем сообщения
    messages = fetch_discord_messages(channel_id, limit=2)
    if not messages:
        return False
    
    found_any = False
    
    for message in messages:
        message_id = message['id']
        
        # Пропускаем если уже обрабатывали
        if message_id in processed_messages_cache:
            continue
        
        # Пропускаем если сообщение старше последнего обработанного
        last_id = last_processed_ids.get(channel_id)
        if last_id and int(message_id) <= int(last_id):
            continue
        
        # Добавляем в кэш (но ограничиваем размер)
        processed_messages_cache.add(message_id)
        if len(processed_messages_cache) > 100:
            # Удаляем самые старые
            oldest = list(processed_messages_cache)[:50]
            for msg_id in oldest:
                processed_messages_cache.remove(msg_id)
        
        # Извлекаем текст
        text = extract_text_from_message(message)
        
        # Ищем целевые предметы для этого канала
        found_items_in_message = []
        
        for item_name, item_config in TARGET_ITEMS.items():
            # Проверяем, отслеживается ли этот предмет в данном канале
            if channel_id not in item_config['channels']:
                continue
            
            # Ищем ключевые слова
            for keyword in item_config['keywords']:
                if keyword.lower() in text:
                    found_items_count[item_name] += 1
                    found_items_in_message.append(item_config)
                    logger.info(f"🎯 Найден {item_config['emoji']} {item_config['display_name']} в {channel_name}!")
                    break
        
        # Обрабатываем найденные предметы
        if found_items_in_message:
            found_any = True
            
            # Отправляем стикер в канал
            for item in found_items_in_message:
                if send_to_channel(sticker_id=item['sticker_id']):
                    # Отправляем уведомление в бота (ТОЛЬКО при находке!)
                    current_time = datetime.now().strftime('%H:%M:%S')
                    notification = f"✅ Найден {item['emoji']} {item['display_name']} в {current_time}"
                    send_to_bot(notification, disable_notification=False)
                    logger.info(f"✅ Стикер {item['emoji']} отправлен в канал")
                else:
                    logger.error(f"❌ Ошибка отправки стикера {item['emoji']}")
        
        # Обновляем последний обработанный ID
        last_processed_ids[channel_id] = message_id
    
    # Сохраняем состояние если что-то нашли
    if found_any:
        save_bot_state()
        logger.debug(f"💾 Состояние сохранено после находки в {channel_name}")
    
    bot_status = f"🟢 Проверен {channel_name}"
    return found_any

# ==================== ПРОСТОЙ МОНИТОРИНГ БЕЗ СЛОЖНОГО РАСПИСАНИЯ ====================
def schedule_monitor():
    """Основной цикл мониторинга - УПРОЩЕННЫЙ"""
    logger.info("👁️‍🗨️ Запуск упрощенного мониторинга...")
    load_bot_state()
    
    # Инициализируем время последней проверки
    last_check_times = {
        SEEDS_CHANNEL_ID: 0,
        EGGS_CHANNEL_ID: 0,
        PASS_SHOP_CHANNEL_ID: 0
    }
    
    # РАЗНЫЕ ИНТЕРВАЛЫ ДЛЯ КАЖДОГО КАНАЛА (в секундах)
    CHECK_INTERVALS = {
        SEEDS_CHANNEL_ID: 180,    # 3 минуты
        EGGS_CHANNEL_ID: 300,     # 5 минут
        PASS_SHOP_CHANNEL_ID: 240 # 4 минуты
    }
    
    # Отправляем стартовое сообщение
    startup_msg = (
        "🚀 <b>УПРОЩЕННЫЙ мониторинг Kiro запущен</b>\n\n"
        "🎯 <b>Отслеживаю:</b>\n"
        "• 🌱 Семена: Tomato, Octobloom, Zebrazinkle, Peppermint Vine\n"
        "• 🥚 Яйца: Gem Egg\n"
        "• 🎫 Пасс-шоп: Pollen Cone\n\n"
        "🔄 <b>Интервалы проверки:</b>\n"
        "• Семена: каждые 3 минуты\n"
        "• Яйца: каждые 5 минут\n"
        "• Пасс-шоп: каждые 4 минуты\n\n"
        "📢 <b>В канал:</b> Только стикеры при находке\n"
        "📱 <b>Вам:</b> Только уведомления о находках\n\n"
        "✅ <b>Защита от лимитов Discord активна</b>"
    )
    send_to_bot(startup_msg)
    
    while True:
        try:
            current_time = time.time()
            
            # Проверяем каждый канал по своему интервалу
            for channel_id in [SEEDS_CHANNEL_ID, EGGS_CHANNEL_ID, PASS_SHOP_CHANNEL_ID]:
                time_since_last = current_time - last_check_times.get(channel_id, 0)
                interval = CHECK_INTERVALS.get(channel_id, 180)
                
                if time_since_last >= interval:
                    channel_name = CHANNEL_NAMES.get(channel_id, channel_id)
                    logger.info(f"🕐 Проверяю {channel_name} (последняя проверка: {time_since_last:.0f} сек назад)...")
                    
                    found = process_discord_messages(channel_id)
                    if found:
                        logger.info(f"✅ В {channel_name} найдены предметы")
                    
                    last_check_times[channel_id] = current_time
                    
                    # Пауза между проверками разных каналов
                    time.sleep(5)  # 5 секунд между запросами
            
            # Пауза между циклами проверки
            logger.debug(f"💤 Ожидаю 30 сек до следующей проверки необходимости...")
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторе: {e}")
            send_to_bot(f"🚨 Ошибка мониторинга: {str(e)[:200]}")
            time.sleep(60)

def status_monitor():
    """Отправляет статус каждые 6 часов"""
    logger.info("📊 Монитор статуса запущен (каждые 6 часов)")
    time.sleep(60)  # Ждем запуска основного монитора
    
    while True:
        try:
            time.sleep(6 * 60 * 60)  # 6 часов
            
            uptime = datetime.now() - bot_start_time
            uptime_hours = uptime.total_seconds() / 3600
            
            # Статистика находок
            items_stats = []
            for item_name, count in found_items_count.items():
                if count > 0:
                    item = TARGET_ITEMS[item_name]
                    items_stats.append(f"{item['emoji']} {item['display_name']}: {count}")
            
            stats_text = "\n".join(items_stats) if items_stats else "Еще не найдено"
            
            # Статус каналов
            channels_status = []
            for channel_id, channel_name in CHANNEL_NAMES.items():
                last_id = last_processed_ids.get(channel_id, 'Не обработано')
                channels_status.append(f"{channel_name}: {last_id}")
            
            status_msg = (
                f"📊 <b>Авто-статус бота (6ч)</b>\n\n"
                f"⏰ Время работы: {uptime_hours:.1f} часов\n"
                f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
                f"🔄 Запросов к Discord: {discord_request_count}\n"
                f"📡 Обработано каналов: {len([x for x in last_processed_ids.values() if x])}/3\n\n"
                f"🎯 <b>Найдено предметов:</b>\n{stats_text}\n\n"
                f"📝 <b>Последние сообщения:</b>\n" + "\n".join(channels_status)
            )
            
            send_to_bot(status_msg)
            logger.info("📊 Отправлен авто-статус")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки статуса: {e}")

def self_pinger():
    """Самопинг для поддержания сервиса онлайн"""
    logger.info("🏓 Самопинг запущен (каждые 8 минут)")
    time.sleep(30)
    
    while True:
        try:
            # Просто логируем, не делаем запросы чтобы не нагружать
            logger.info("🏓 Самопинг: сервис активен")
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
        
        time.sleep(8 * 60)  # 8 минут

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    """Главная страница"""
    uptime = datetime.now() - bot_start_time
    uptime_str = str(uptime).split('.')[0]
    
    # Статистика находок
    found_items = []
    for item_name, count in found_items_count.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            found_items.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    return f"""
    <html>
    <head>
        <title>🌱 Упрощенный мониторинг Kiro</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .card {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .status-ok {{ color: #2ecc71; }}
            .button {{ 
                display: inline-block; 
                padding: 10px 20px; 
                margin: 5px; 
                background: #3498db; 
                color: white; 
                text-decoration: none; 
                border-radius: 5px;
            }}
            .button-disable {{ background: #e74c3c; }}
            .button-enable {{ background: #2ecc71; }}
        </style>
    </head>
    <body>
        <h1>🌱 Упрощенный мониторинг Kiro</h1>
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> <span class="status-ok">{bot_status}</span></p>
            <p><strong>Время работы:</strong> {uptime_str}</p>
            <p><strong>Telegram-канал:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</p>
            <p><strong>Запросов к Discord:</strong> {discord_request_count}</p>
            <p><strong>В кэше сообщений:</strong> {len(processed_messages_cache)}</p>
        </div>
        
        <div class="card">
            <h2>🎯 Управление</h2>
            <a href="/enable" class="button button-enable">✅ Включить канал</a>
            <a href="/disable" class="button button-disable">⏸️ Выключить канал</a>
            <a href="/status" class="button">📊 Статус</a>
        </div>
        
        <div class="card">
            <h2>📡 Отслеживаемые каналы</h2>
            <ul>
                <li><strong>🌱 Семена (каждые 3 мин):</strong> Tomato, Octobloom, Zebrazinkle, Peppermint Vine</li>
                <li><strong>🥚 Яйца (каждые 5 мин):</strong> Gem Egg</li>
                <li><strong>🎫 Пасс-шоп (каждые 4 мин):</strong> Pollen Cone</li>
            </ul>
        </div>
        
        <div class="card">
            <h2>🏆 Найдено предметов</h2>
            <ul>{"".join([f'<li>{item}</li>' for item in found_items]) if found_items else '<li>Еще не найдено</li>'}</ul>
        </div>
        
        <div class="card">
            <h2>📱 Логика работы</h2>
            <p><strong>📢 В Telegram-канал:</strong> Только стикеры при находке предметов</p>
            <p><strong>🤖 Вам в бота:</strong> Только уведомления "✅ Найден [предмет]"</p>
            <p><strong>🔄 Расписание:</strong> Упрощенное с защитой от лимитов</p>
            <p><strong>💾 Сохранение:</strong> Состояние сохраняется между перезапусками</p>
        </div>
    </body>
    </html>
    """

@app.route('/enable')
def enable_channel():
    """Включить отправку в канал"""
    global channel_enabled
    channel_enabled = True
    send_to_bot("✅ <b>Отправка стикеров в канал ВКЛЮЧЕНА</b>")
    return "✅ Отправка стикеров в канал включена"

@app.route('/disable')
def disable_channel():
    """Выключить отправку в канал"""
    global channel_enabled
    channel_enabled = False
    send_to_bot("⏸️ <b>Отправка стикеров в канал ВЫКЛЮЧЕНА</b>")
    return "⏸️ Отправка стикеров в канал выключена"

@app.route('/status')
def status_page():
    """Страница статуса"""
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
        channels_info.append(f"{channel_name}: {last_id}")
    
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
            <p><strong>Последние сообщения:</strong></p>
            <pre>{"\\n".join(channels_info)}</pre>
            <p><a href="/">← Назад</a></p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health_check():
    """Проверка здоровья сервиса"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': (datetime.now() - bot_start_time).total_seconds(),
        'discord_requests': discord_request_count,
        'channel_enabled': channel_enabled,
        'processed_messages': len(processed_messages_cache)
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК УПРОЩЕННОГО МОНИТОРИНГА KIRO")
    logger.info("=" * 60)
    logger.info("📱 Telegram-бот: Только уведомления о находках")
    logger.info("📢 Telegram-канал: Только стикеры при находке")
    logger.info("🎯 Отслеживаю 6 предметов в 3 каналах")
    logger.info("🔄 Интервалы: Семена-3мин, Яйца-5мин, Пасс-шоп-4мин")
    logger.info("🛡️ Защита от лимитов Discord: 1 запрос/10 секунд")
    logger.info("💾 Сохранение состояния: ВКЛЮЧЕНО")
    logger.info("=" * 60)
    
    # Запускаем фоновые потоки
    threads = [
        threading.Thread(target=schedule_monitor, name='ScheduleMonitor', daemon=True),
        threading.Thread(target=status_monitor, name='StatusMonitor', daemon=True),
        threading.Thread(target=self_pinger, name='SelfPinger', daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Запущен поток: {thread.name}")
        time.sleep(1)
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
