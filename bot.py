from flask import Flask
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
import re
import json
import random

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
SEEDS_CHANNEL_ID = os.getenv('SEEDS_CHANNEL_ID')  # ⬅️ ВАЖНО: ТОЛЬКО СЕМЕНА!
# EVENT_SHOP_CHANNEL_ID = os.getenv('EVENT_SHOP_CHANNEL_ID')  # ⬅️ НЕ ИСПОЛЬЗУЕМ
# PASS_SHOP_CHANNEL_ID = os.getenv('PASS_SHOP_CHANNEL_ID')    # ⬅️ НЕ ИСПОЛЬЗУЕМ
RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://your-bot.onrender.com')

# ==================== СЕМЕНА ДЛЯ ОТСЛЕЖИВАНИЯ ====================
TARGET_ITEMS = {
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
    'firework_fern': {
        'keywords': ['firework fern', 'fireworkfern', ':fireworkfern', ':firework_fern:'],
        'sticker_id': "CAACAgIAAxkBAAEQHChpUBeOda8Uf0Uwig6BwvkW_z1ndAAC5Y0AAl8dgEoandjqAtpRWTYE",
        'emoji': '🎆',
        'display_name': 'Firework Fern'
    },
    # ТЕСТОВЫЙ ПРЕДМЕТ - частый в стоке
    'tomato_seeds': {
        'keywords': ['tomato seed', 'tomato seeds', 'томат', 'томаты', 'томатное семя'],
        'sticker_id': "CAACAgIAAxkBAAEPtFBpCrZ_mxXMfMmrjTZkBHN3Tpn9OAACf3sAAoEeWUgkKobs-st7ojYE",
        'emoji': '🍅',
        'display_name': 'Tomato Seeds (TEST)'
    }
}

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
bot_start_time = datetime.now()
bot_status = "🟢 Инициализация"
channel_enabled = True
found_items_count = {name: 0 for name in TARGET_ITEMS.keys()}
ping_count = 0
last_ping_time = None
telegram_offset = 0
last_error = None

# НОВЫЕ ПЕРЕМЕННЫЕ ДЛЯ УМНЫХ ЦИКЛОВ
current_cycle_start = None  # Время начала текущего 5-минутного цикла
cycle_found_stock = False   # Найден ли сток в текущем цикле
last_kiro_message_time = None  # Время последнего сообщения от Kiro
last_processed_message_id = None  # ID последнего обработанного сообщения
SAFE_INTERVAL = 30  # Проверять каждые 30 секунд в цикле

# УСИЛЕННЫЙ АВАРИЙНЫЙ РЕЖИМ DISCORD
discord_emergency_mode = False
discord_emergency_start = None
discord_error_count = 0
discord_last_error_time = None
EMERGENCY_COOLDOWN = 3600  # 1 ЧАС в секундах
MAX_ERRORS_BEFORE_EMERGENCY = 2  # Только 2 ошибки подряд
ERROR_WINDOW_SECONDS = 300  # Окно для подсчёта ошибок: 5 минут

# Защита от дублирования стикеров в одном цикле
sent_stickers_this_cycle = set()

# Файл для сохранения состояния
STATE_FILE = 'bot_state.json'

# ==================== СОХРАНЕНИЕ СОСТОЯНИЯ ====================
def save_state():
    """Сохраняет состояние бота"""
    try:
        state = {
            'found_items_count': found_items_count,
            'last_kiro_message_time': last_kiro_message_time.isoformat() if last_kiro_message_time else None,
            'last_processed_message_id': last_processed_message_id,
            'ping_count': ping_count,
            'bot_status': bot_status,
            'discord_emergency_mode': discord_emergency_mode,
            'discord_emergency_start': discord_emergency_start.isoformat() if discord_emergency_start else None,
            'discord_error_count': discord_error_count,
            'discord_last_error_time': discord_last_error_time
        }
        
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
        
        logger.debug("💾 Состояние сохранено")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения состояния: {e}")

def load_state():
    """Загружает состояние бота"""
    global found_items_count, last_kiro_message_time, last_processed_message_id
    global ping_count, bot_status, discord_emergency_mode, discord_emergency_start
    global discord_error_count, discord_last_error_time
    
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
            
            found_items_count = state.get('found_items_count', found_items_count)
            ping_count = state.get('ping_count', ping_count)
            bot_status = state.get('bot_status', bot_status)
            last_processed_message_id = state.get('last_processed_message_id')
            
            # Восстанавливаем время
            time_str = state.get('last_kiro_message_time')
            if time_str:
                last_kiro_message_time = datetime.fromisoformat(time_str)
            
            # Восстанавливаем аварийный режим
            discord_emergency_mode = state.get('discord_emergency_mode', False)
            emergency_start_str = state.get('discord_emergency_start')
            if emergency_start_str:
                discord_emergency_start = datetime.fromisoformat(emergency_start_str)
            discord_error_count = state.get('discord_error_count', 0)
            discord_last_error_time = state.get('discord_last_error_time')
            
            if discord_emergency_mode:
                logger.warning("🚨 Загружен аварийный режим Discord из состояния")
            
            logger.info("💾 Состояние загружено")
        else:
            logger.info("📂 Файл состояния не найден, начинаем с чистого листа")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки состояния: {e}")

# ==================== УСИЛЕННЫЙ АВАРИЙНЫЙ РЕЖИМ DISCORD ====================
def update_error_count():
    """Обновляет счётчик ошибок Discord"""
    global discord_error_count, discord_last_error_time
    
    current_time = time.time()
    
    # Если прошло больше ERROR_WINDOW_SECONDS, сбрасываем счётчик
    if discord_last_error_time and (current_time - discord_last_error_time > ERROR_WINDOW_SECONDS):
        discord_error_count = 0
        logger.info("🔄 Счётчик ошибок Discord сброшен")
    
    discord_error_count += 1
    discord_last_error_time = current_time
    
    logger.warning(f"⚠️ Ошибка Discord #{discord_error_count}")
    
    if discord_error_count >= MAX_ERRORS_BEFORE_EMERGENCY:
        activate_emergency_mode()

def activate_emergency_mode():
    """Активирует аварийный режим (1 час)"""
    global discord_emergency_mode, discord_emergency_start, discord_error_count
    
    if not discord_emergency_mode:
        discord_emergency_mode = True
        discord_emergency_start = datetime.now()
        discord_error_count = 0
        
        emergency_msg = (
            f"🚨 <b>АВАРИЙНЫЙ РЕЖИМ DISCORD АКТИВИРОВАН</b>\n\n"
            f"• Причина: {MAX_ERRORS_BEFORE_EMERGENCY} ошибки Discord подряд\n"
            f"• Время начала: {discord_emergency_start.strftime('%H:%M:%S')}\n"
            f"• Перерыв: 1 ЧАС (усиленная защита)\n"
            f"• Все запросы к Discord приостановлены\n"
            f"• Самопинг и команды продолжают работать\n\n"
            f"Автоматическое восстановление через 1 час."
        )
        
        send_to_bot(emergency_msg)
        logger.error(f"🚨 Аварийный режим Discord активирован! Перерыв 1 ЧАС.")
        
        save_state()

def check_emergency_mode():
    """Проверяет, можно ли выйти из аварийного режима"""
    global discord_emergency_mode, discord_emergency_start
    
    if discord_emergency_mode and discord_emergency_start:
        time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
        
        if time_in_emergency >= EMERGENCY_COOLDOWN:
            # Выходим из аварийного режима
            discord_emergency_mode = False
            discord_emergency_start = None
            
            recovery_msg = (
                f"✅ <b>АВАРИЙНЫЙ РЕЖИМ DISCORD ОТКЛЮЧЁН</b>\n\n"
                f"• Аварийный режим длился: {time_in_emergency/3600:.1f} часов\n"
                f"• Время восстановления: {datetime.now().strftime('%H:%M:%S')}\n"
                f"• Запросы к Discord возобновлены\n"
                f"• Мониторинг продолжает работу"
            )
            
            send_to_bot(recovery_msg)
            logger.info("✅ Аварийный режим Discord отключён. Возобновляю работу.")
            
            save_state()
            return True
        else:
            remaining = EMERGENCY_COOLDOWN - time_in_emergency
            minutes_left = remaining / 60
            logger.warning(f"🚨 Аварийный режим Discord: осталось {minutes_left:.1f} минут")
            return False
    
    return True

# ==================== УЛУЧШЕННАЯ РАБОТА С ЦИКЛАМИ ====================
def get_current_cycle_start():
    """Возвращает время начала текущего 5-минутного цикла"""
    now = datetime.now()
    cycle_minute = (now.minute // 5) * 5
    return now.replace(minute=cycle_minute, second=0, microsecond=0)

def parse_discord_timestamp(timestamp_str):
    """Парсит Discord timestamp в datetime"""
    try:
        if not timestamp_str:
            return None
        
        clean_str = timestamp_str
        
        if '.' in clean_str:
            clean_str = clean_str.split('.')[0]
        
        if clean_str.endswith('Z'):
            clean_str = clean_str[:-1] + '+00:00'
        
        return datetime.fromisoformat(clean_str)
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга timestamp '{timestamp_str}': {e}")
        return None

def is_message_for_current_cycle(message, current_cycle_start_time):
    """
    УЛУЧШЕННАЯ ПРОВЕРКА: Определяет, относится ли сообщение к текущему циклу
    С учетом "окна" в 30 секунд из предыдущего цикла
    """
    try:
        timestamp_str = message.get('timestamp')
        if not timestamp_str:
            return True
        
        message_time = parse_discord_timestamp(timestamp_str)
        if not message_time:
            return True
        
        # Текущий цикл начался в current_cycle_start_time
        # Предыдущий цикл закончился за 30 секунд до этого
        previous_cycle_window_start = current_cycle_start_time - timedelta(seconds=30)
        
        # Сообщение актуально если:
        # 1. Отправлено ПОСЛЕ начала текущего цикла
        # 2. ИЛИ отправлено в последние 30 секунд предыдущего цикла
        is_relevant = message_time >= previous_cycle_window_start
        
        return is_relevant
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки timestamp: {e}")
        return True

def should_check_now():
    """
    Определяет, нужно ли проверять прямо сейчас
    Возвращает: (should_check, seconds_until_next_cycle)
    """
    global current_cycle_start, cycle_found_stock
    
    # Проверяем аварийный режим
    if not check_emergency_mode():
        logger.debug("⏸️ Аварийный режим активен - пропускаем проверку")
        return False, 60
    
    now = datetime.now()
    current_cycle = get_current_cycle_start()
    
    # Если начался новый цикл
    if current_cycle_start != current_cycle:
        logger.info(f"🔄 Новый цикл начался: {current_cycle.strftime('%H:%M:%S')}")
        current_cycle_start = current_cycle
        cycle_found_stock = False
        sent_stickers_this_cycle.clear()
    
    # Если в этом цикле уже нашли/обработали сообщение Kiro - не проверяем
    if cycle_found_stock:
        next_cycle = current_cycle + timedelta(minutes=5)
        seconds_left = (next_cycle - now).total_seconds()
        
        if seconds_left > 0:
            logger.debug(f"⏸️ Сообщение Kiro в этом цикле уже обработано. До следующего: {seconds_left:.0f} сек")
            return False, min(seconds_left, 60)
        return False, 1
    
    # Проверяем каждые 30 секунд внутри цикла
    seconds_in_cycle = (now - current_cycle_start).total_seconds()
    
    # Проверяем каждые SAFE_INTERVAL секунд
    check_window = 3
    seconds_mod = seconds_in_cycle % SAFE_INTERVAL
    
    if seconds_mod < check_window:
        seconds_until_next_check = SAFE_INTERVAL - seconds_mod
        return True, seconds_until_next_check
    
    seconds_to_next_check = SAFE_INTERVAL - (seconds_in_cycle % SAFE_INTERVAL)
    return False, min(seconds_to_next_check, 60)

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
            logger.warning(f"⚠️ Лимит Telegram стикеров, жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Ошибка отправки стикера {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки стикера: {e}")
        return False

def send_to_channel(sticker_id=None, text=None):
    """Отправка в канал с защитой от спама"""
    if not channel_enabled or not TELEGRAM_CHANNEL_ID:
        return False
    
    if not hasattr(send_to_channel, 'last_send_time'):
        send_to_channel.last_send_time = 0
    
    current_time = time.time()
    if current_time - send_to_channel.last_send_time < 2:
        time.sleep(2)
    
    send_to_channel.last_send_time = time.time()
    
    if sticker_id:
        return send_telegram_sticker(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    
    return False

def send_to_bot(text, disable_notification=False):
    """Отправляет сообщение в личные сообщения бота"""
    if not TELEGRAM_BOT_CHAT_ID:
        return False
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text, disable_notification=disable_notification)

# ==================== DISCORD ФУНКЦИИ ====================
def safe_discord_request(limit=10):
    """Безопасный запрос к Discord API - ТОЛЬКО КАНАЛ С СЕМЕНАМИ"""
    global last_error
    
    if not DISCORD_TOKEN or not SEEDS_CHANNEL_ID:  # ⬅️ ИСПОЛЬЗУЕМ SEEDS_CHANNEL_ID
        return None
    
    # Проверяем аварийный режим
    if not check_emergency_mode():
        return None
    
    try:
        # Случайная задержка 1-3 секунды перед запросом
        time.sleep(1 + random.random() * 2)
        
        # ⬅️ ВАЖНО: Используем SEEDS_CHANNEL_ID вместо DISCORD_CHANNEL_ID
        url = f"https://discord.com/api/v10/channels/{SEEDS_CHANNEL_ID}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            last_error = None
            return response.json()
        elif response.status_code == 429:
            retry_after = response.json().get('retry_after', 5.0)
            last_error = f"Discord 429: жду {retry_after} сек"
            logger.warning(f"⏳ Discord API лимит. Жду {retry_after} сек.")
            
            update_error_count()
            time.sleep(retry_after + 3)
            return None
        else:
            last_error = f"Discord ошибка {response.status_code}"
            logger.error(f"❌ Ошибка Discord API {response.status_code}")
            
            update_error_count()
            return None
    except Exception as e:
        last_error = f"Ошибка Discord: {e}"
        logger.error(f"❌ Ошибка Discord запроса: {e}")
        
        update_error_count()
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

def process_discord_messages():
    """Обработка сообщений Discord - ТОЛЬКО КАНАЛ С СЕМЕНАМИ"""
    global cycle_found_stock, last_kiro_message_time, last_processed_message_id
    global found_items_count, bot_status, last_error
    
    # Проверяем аварийный режим
    if not check_emergency_mode():
        return False
    
    messages = safe_discord_request(limit=10)  # ⬅️ Запрос к каналу с семенами
    if not messages:
        return False
    
    found_any_item = False
    current_time = datetime.now()
    current_cycle_start_time = get_current_cycle_start()
    
    # Сортируем от старых к новым
    messages.sort(key=lambda x: x['id'], reverse=False)
    
    for message in messages:
        message_id = message['id']
        
        # Пропускаем уже обработанные сообщения
        if last_processed_message_id and int(message_id) <= int(last_processed_message_id):
            continue
        
        author_name = message.get('author', {}).get('username', '').lower()
        
        # Ищем только сообщения от Kiro
        if 'kiro' not in author_name:
            continue
        
        # УЛУЧШЕННАЯ ПРОВЕРКА: относится ли сообщение к текущему циклу?
        if not is_message_for_current_cycle(message, current_cycle_start_time):
            logger.info(f"⏪ Пропускаем сообщение {message_id} - не относится к текущему циклу")
            last_processed_message_id = message_id
            continue
        
        # НАШЛИ Kiro и сообщение актуально!
        logger.info(f"🎯 Найдено актуальное сообщение от Kiro в канале семян: {message_id}")
        
        # Обновляем время последнего сообщения Kiro
        last_kiro_message_time = current_time
        last_processed_message_id = message_id
        
        # Извлекаем текст
        text = extract_text_from_message(message)
        
        # Проверяем на наличие семян
        found_items_this_message = []
        
        for item_name, item_config in TARGET_ITEMS.items():
            for keyword in item_config['keywords']:
                if keyword in text:
                    found_items_count[item_name] += 1
                    found_items_this_message.append(item_config)
                    break
        
        # Если нашли семена - отправляем уведомления
        if found_items_this_message:
            logger.info(f"✅ Найдены семена в сообщении {message_id}")
            
            for item_config in found_items_this_message:
                # Проверяем, не отправляли ли уже этот стикер в этом цикле
                if item_config['sticker_id'] in sent_stickers_this_cycle:
                    logger.info(f"⏭️ Стикер {item_config['emoji']} уже отправлен в этом цикле, пропускаем")
                    continue
                
                # Отправляем в личные сообщения
                time_str = current_time.strftime('%H:%M:%S')
                cycle_str = current_cycle_start_time.strftime('%H:%M')
                
                notification = (
                    f"🎯 <b>НАЙДЕН {item_config['emoji']} {item_config['display_name']}</b>\n"
                    f"Время: {time_str}\n"
                    f"Цикл: {cycle_str}\n"
                    f"Канал: 🌱 Семена\n"
                    f"ID: {message_id}"
                )
                
                send_to_bot(notification, disable_notification=False)
                
                # Отправляем стикер в канал
                if send_to_channel(sticker_id=item_config['sticker_id']):
                    logger.info(f"📢 Стикер {item_config['emoji']} отправлен в канал")
                    sent_stickers_this_cycle.add(item_config['sticker_id'])
                
                found_any_item = True
            
            # Останавливаем проверки в этом цикле
            cycle_found_stock = True
            bot_status = f"🟢 Найден сток в цикле {current_cycle_start_time.strftime('%H:%M')}"
            
            save_state()
            return True
        
        # Если Kiro отправил сообщение, но семян нет
        logger.info(f"📭 Kiro отправил сообщение без нужных семян")
        
        # Останавливаем проверки в этом цикле
        cycle_found_stock = True
        bot_status = f"🟡 Kiro без семян в цикле {current_cycle_start_time.strftime('%H:%M')}"
        
        # Отправляем уведомление в личку
        time_str = current_time.strftime('%H:%M:%S')
        empty_notification = (
            f"📭 <b>Kiro отправил сообщение без нужных семян</b>\n"
            f"Время: {time_str}\n"
            f"Цикл: {current_cycle_start_time.strftime('%H:%M')}\n"
            f"Канал: 🌱 Семена\n"
            f"ID: {message_id}\n\n"
            f"Проверки остановлены до следующего цикла."
        )
        send_to_bot(empty_notification, disable_notification=True)
        
        save_state()
        return True
    
    # Не нашли новых актуальных сообщений от Kiro
    logger.debug("📭 Новых актуальных сообщений от Kiro не найдено")
    return False

# ==================== ОСНОВНОЙ МОНИТОРИНГ ====================
def smart_monitor():
    """Умный мониторинг с 5-минутными циклами - ТОЛЬКО СЕМЕНА"""
    logger.info("🌱 Запуск мониторинга КАНАЛА С СЕМЕНАМИ (5-минутные циклы)")
    
    # Ждем до начала следующего 5-минутного цикла
    now = datetime.now()
    next_cycle = get_current_cycle_start() + timedelta(minutes=5)
    seconds_to_wait = (next_cycle - now).total_seconds()
    
    if seconds_to_wait > 0:
        logger.info(f"⏳ Жду начала следующего цикла: {seconds_to_wait:.0f} сек")
        time.sleep(min(seconds_to_wait, 60))
    
    while True:
        try:
            # Определяем, нужно ли проверять сейчас
            should_check, wait_seconds = should_check_now()
            
            if should_check:
                current_cycle_str = get_current_cycle_start().strftime('%H:%M')
                logger.info(f"🔍 Проверяю Discord (🌱 Семена, цикл {current_cycle_str})")
                
                # Делаем запрос к Discord (ТОЛЬКО канал с семенами)
                found = process_discord_messages()
                
                if found:
                    logger.info("✅ Сообщение Kiro обработано! Останавливаю проверки до следующего цикла")
                else:
                    logger.info("📭 Актуальных сообщений Kiro не найдено, жду следующей проверки")
            
            # Умное ожидание
            if wait_seconds > 0:
                logger.debug(f"💤 Следующая проверка через {wait_seconds:.0f} сек")
                time.sleep(min(wait_seconds, 5))
            else:
                time.sleep(1)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторе семян: {e}")
            time.sleep(10)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def self_pinger():
    """Самопинг для Render"""
    global ping_count, last_ping_time
    
    logger.info("🏓 Запуск самопинга (каждые 8 минут)")
    
    time.sleep(30)
    
    while True:
        try:
            ping_count += 1
            last_ping_time = datetime.now()
            logger.info(f"🏓 Самопинг #{ping_count}...")
            
            response = requests.get(f"{RENDER_SERVICE_URL}/", timeout=10)
            if response.status_code == 200:
                logger.info("✅ Самопинг успешен")
            else:
                logger.warning(f"⚠️ Самопинг: статус {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
        
        logger.info("💤 Ожидаю 8 минут до следующего самопинга...")
        time.sleep(480)

def telegram_poller():
    """Опросщик Telegram команд"""
    global telegram_offset
    
    logger.info("🔍 Запуск Telegram поллера...")
    
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
                            
                            if text.startswith('/'):
                                if text == '/status':
                                    send_bot_status(chat_id)
                                elif text == '/start':
                                    send_welcome_message(chat_id)
                                elif text == '/emergency_info':
                                    send_emergency_info(chat_id)
                                elif text == '/reset_errors':
                                    reset_error_counter(chat_id)
                
                time.sleep(5)
            else:
                time.sleep(10)
            
        except Exception as e:
            logger.error(f"💥 Ошибка Telegram поллера: {e}")
            time.sleep(10)

def reset_error_counter(chat_id):
    """Сброс счетчика ошибок (админская команда)"""
    global discord_error_count, discord_last_error_time
    discord_error_count = 0
    discord_last_error_time = None
    send_telegram_message(chat_id, "✅ Счетчик ошибок Discord сброшен")
    save_state()

def send_bot_status(chat_id):
    """Отправляет статус бота"""
    global bot_status, last_error, channel_enabled, ping_count
    global found_items_count, current_cycle_start, cycle_found_stock
    global last_kiro_message_time, discord_emergency_mode, discord_emergency_start
    global discord_error_count
    
    uptime = datetime.now() - bot_start_time
    hours = uptime.total_seconds() / 3600
    
    items_stats = "\n".join([f"{config['emoji']} {config['display_name']}: {found_items_count[name]} раз" 
                           for name, config in TARGET_ITEMS.items() if found_items_count[name] > 0])
    
    cycle_info = ""
    if current_cycle_start:
        now = datetime.now()
        cycle_info = f"\n📅 <b>Текущий цикл:</b> {current_cycle_start.strftime('%H:%M')}\n"
        
        if cycle_found_stock:
            cycle_info += "✅ <b>Сообщение Kiro в этом цикле уже обработано</b>\n"
        else:
            seconds_in_cycle = (now - current_cycle_start).total_seconds()
            checks_done = int(seconds_in_cycle // SAFE_INTERVAL) + 1
            cycle_info += f"🔍 <b>Проверок в цикле:</b> {checks_done}\n"
        
        if last_kiro_message_time:
            time_since_last = (now - last_kiro_message_time).total_seconds()
            cycle_info += f"⏰ <b>Последний Kiro:</b> {last_kiro_message_time.strftime('%H:%M:%S')} ({time_since_last:.0f} сек назад)\n"
    
    emergency_info = ""
    if discord_emergency_mode and discord_emergency_start:
        time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
        remaining = max(0, EMERGENCY_COOLDOWN - time_in_emergency)
        emergency_info = (
            f"\n\n🚨 <b>АВАРИЙНЫЙ РЕЖИМ DISCORD АКТИВЕН</b>\n"
            f"• Начало: {discord_emergency_start.strftime('%H:%M:%S')}\n"
            f"• Прошло: {time_in_emergency/60:.1f} минут\n"
            f"• Осталось: {remaining/60:.1f} минут\n"
            f"• Все запросы к Discord приостановлены\n"
            f"• Следующая проверка через {remaining/60:.1f} минут"
        )
    else:
        emergency_info = f"\n\n🛡️ <b>Аварийный режим:</b> ✅ ОТКЛЮЧЁН (ошибок: {discord_error_count}/{MAX_ERRORS_BEFORE_EMERGENCY})"
    
    status_text = (
        f"🤖 <b>СТАТУС БОТА (ТОЛЬКО СЕМЕНА)</b>\n\n"
        f"{bot_status}\n"
        f"⏰ <b>Время работы:</b> {hours:.1f} часов\n"
        f"📢 <b>Канал:</b> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"🏓 <b>Самопинг:</b> {ping_count} раз\n"
        f"🌱 <b>Отслеживаю:</b> ТОЛЬКО канал с семенами\n"
        f"{cycle_info}"
        f"{emergency_info}\n\n"
        f"🎯 <b>Найдено семян:</b>\n"
        f"{items_stats if items_stats else 'Еще не найдено'}\n\n"
        f"⚙️ <b>Настройки защиты:</b>\n"
        f"• {MAX_ERRORS_BEFORE_EMERGENCY} ошибки Discord → 1 час перерыва\n"
        f"• Умная проверка времени сообщений (+30 сек окно)\n"
        f"• 5-минутные циклы с остановкой после Kiro"
    )
    
    if last_error:
        status_text += f"\n\n⚠️ <b>Последняя ошибка:</b>\n<code>{last_error}</code>"
    
    send_telegram_message(chat_id, status_text)

def send_welcome_message(chat_id):
    """Отправляет приветственное сообщение"""
    welcome_text = (
        f"🤖 <b>УМНЫЙ МОНИТОРИНГ KIRO (ТОЛЬКО СЕМЕНА)</b>\n\n"
        f"🎯 <b>Отслеживаю семена:</b>\n"
        f"• 🐙 Octobloom\n"
        f"• 🦓 Zebrazinkle\n"
        f"• 🎆 Firework Fern\n"
        f"• 🍅 Tomato Seeds (тестовый, частый)\n\n"
        f"🌱 <b>Отслеживаю только канал с семенами</b>\n"
        f"• Ивент-шоп: ❌ НЕ отслеживается\n"
        f"• Пасс-шоп: ❌ НЕ отслеживается\n\n"
        f"🔄 <b>Улучшенная логика работы:</b>\n"
        f"• 5-минутные циклы (00:00, 00:05...)\n"
        f"• Проверка каждые 30 секунд в цикле\n"
        f"• Остановка после ЛЮБОГО сообщения Kiro\n"
        f"• Умная проверка времени (+30 сек окно)\n\n"
        f"🛡️ <b>УСИЛЕННЫЙ АВАРИЙНЫЙ РЕЖИМ:</b>\n"
        f"• {MAX_ERRORS_BEFORE_EMERGENCY} ошибки Discord → 1 ЧАС перерыва\n"
        f"• Автоматическое восстановление\n\n"
        f"📊 <b>Команды:</b>\n"
        f"/status - текущий статус\n"
        f"/emergency_info - информация об аварийном режиме\n"
        f"/reset_errors - сброс счетчика ошибок (админ)\n\n"
        f"✅ <b>Бот работает с максимальной защитой</b>"
    )
    send_telegram_message(chat_id, welcome_text)

def send_emergency_info(chat_id):
    """Отправляет информацию об аварийном режиме"""
    global discord_emergency_mode, discord_emergency_start, discord_error_count
    
    if discord_emergency_mode and discord_emergency_start:
        time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
        remaining = max(0, EMERGENCY_COOLDOWN - time_in_emergency)
        
        emergency_text = (
            f"🚨 <b>АВАРИЙНЫЙ РЕЖИМ DISCORD АКТИВЕН (УСИЛЕННЫЙ)</b>\n\n"
            f"• Причина: {MAX_ERRORS_BEFORE_EMERGENCY} ошибки Discord подряд\n"
            f"• Активирован: {discord_emergency_start.strftime('%H:%M:%S')}\n"
            f"• Прошло: {time_in_emergency/60:.1f} минут\n"
            f"• Осталось: {remaining/60:.1f} минут\n"
            f"• Все запросы к Discord приостановлены\n\n"
            f"🛡️ <b>Усиленная защита: 1 ЧАС перерыва</b>\n"
            f"✅ Автоматическое восстановление через {remaining/60:.1f} минут"
        )
    else:
        emergency_text = (
            f"✅ <b>АВАРИЙНЫЙ РЕЖИМ DISCORD ОТКЛЮЧЁН</b>\n\n"
            f"• Все системы работают нормально\n"
            f"• Текущих ошибок Discord: {discord_error_count}\n"
            f"• Лимит для активации: {MAX_ERRORS_BEFORE_EMERGENCY} ошибки подряд\n"
            f"• Длительность аварийного режима: 1 ЧАС\n\n"
            f"⚡ <b>Усиленная защита активна</b>"
        )
    
    send_telegram_message(chat_id, emergency_text)

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    uptime = datetime.now() - bot_start_time
    uptime_str = str(uptime).split('.')[0]
    
    items_list = []
    for item_name, count in found_items_count.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            items_list.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    cycle_info = ""
    if current_cycle_start:
        now = datetime.now()
        cycle_info = f"<p><strong>Текущий цикл:</strong> {current_cycle_start.strftime('%H:%M')}</p>"
        
        if cycle_found_stock:
            cycle_info += "<p style='color: green;'>✅ Сообщение Kiro в этом цикле уже обработано</p>"
        else:
            seconds_in_cycle = (now - current_cycle_start).total_seconds()
            next_check_in = SAFE_INTERVAL - (seconds_in_cycle % SAFE_INTERVAL)
            cycle_info += f"<p><strong>Следующая проверка:</strong> через {next_check_in:.0f} сек</p>"
    
    emergency_info = ""
    if discord_emergency_mode and discord_emergency_start:
        time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
        remaining = max(0, EMERGENCY_COOLDOWN - time_in_emergency)
        emergency_info = f"""
        <div class="card" style="background: #ffcccc;">
            <h2>🚨 АВАРИЙНЫЙ РЕЖИМ DISCORD (УСИЛЕННЫЙ)</h2>
            <p><strong>Статус:</strong> 🚨 АКТИВЕН</p>
            <p><strong>Начало:</strong> {discord_emergency_start.strftime('%H:%M:%S')}</p>
            <p><strong>Прошло:</strong> {time_in_emergency/60:.1f} минут</p>
            <p><strong>Осталось:</strong> {remaining/60:.1f} минут</p>
            <p><strong>Длительность:</strong> 1 ЧАС (усиленная защита)</p>
            <p><strong>Все запросы к Discord приостановлены</strong></p>
        </div>
        """
    else:
        emergency_info = f"""
        <div class="card" style="background: #e8f5e8;">
            <h2>🛡️ Аварийный режим Discord</h2>
            <p><strong>Статус:</strong> ✅ ОТКЛЮЧЁН</p>
            <p><strong>Текущих ошибок:</strong> {discord_error_count}/{MAX_ERRORS_BEFORE_EMERGENCY}</p>
            <p><strong>Лимит активации:</strong> {MAX_ERRORS_BEFORE_EMERGENCY} ошибки подряд</p>
            <p><strong>Длительность:</strong> 1 ЧАС (усиленная защита)</p>
            <p><strong>Система защиты активна</strong></p>
        </div>
        """
    
    return f"""
    <html>
    <head>
        <title>🌱 Мониторинг Kiro (ТОЛЬКО СЕМЕНА)</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .card {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .status-ok {{ color: #2ecc71; }}
            .status-emergency {{ color: #e74c3c; }}
            .seeds-only {{ background: #e8f5e8; padding: 15px; border-radius: 8px; margin: 10px 0; }}
            .protection {{ background: #fff3cd; padding: 15px; border-radius: 8px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <h1>🌱 Умный мониторинг Kiro (ТОЛЬКО СЕМЕНА)</h1>
        
        {emergency_info}
        
        <div class="seeds-only">
            <h2>🌱 ОТСЛЕЖИВАЕТСЯ ТОЛЬКО КАНАЛ С СЕМЕНАМИ</h2>
            <p><strong>Канал семян:</strong> ✅ АКТИВЕН</p>
            <p><strong>Ивент-шоп:</strong> ❌ НЕ отслеживается</p>
            <p><strong>Пасс-шоп:</strong> ❌ НЕ отслеживается</p>
            <p><strong>Частота:</strong> 5-минутные циклы, проверка каждые 30 сек</p>
        </div>
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> <span class="status-ok">{bot_status}</span></p>
            <p><strong>Время работы:</strong> {uptime_str}</p>
            <p><strong>Самопингов:</strong> {ping_count}</p>
            {cycle_info}
            <p><strong>Последний ID:</strong> {last_processed_message_id or 'Нет'}</p>
        </div>
        
        <div class="protection">
            <h2>⚙️ Усиленные настройки защиты</h2>
            <p><strong>Аварийный режим:</strong> {MAX_ERRORS_BEFORE_EMERGENCY} ошибки → 1 ЧАС перерыва</p>
            <p><strong>Проверка времени:</strong> Умное окно (+30 секунд из предыдущего цикла)</p>
            <p><strong>Циклы:</strong> 5-минутные с остановкой после ЛЮБОГО сообщения Kiro</p>
            <p><strong>Запросы:</strong> Минимум (1-3 за цикл) для избежания блокировок</p>
        </div>
        
        <div class="card">
            <h2>🎯 Отслеживаемые семена</h2>
            <ul>
                <li>🐙 Octobloom</li>
                <li>🦓 Zebrazinkle</li>
                <li>🎆 Firework Fern</li>
                <li>🍅 Tomato Seeds (тестовый, частый)</li>
            </ul>
        </div>
        
        <div class="card">
            <h2>🔄 Улучшенная логика работы</h2>
            <p><strong>5-минутные циклы:</strong> 00:00, 00:05, 00:10...</p>
            <p><strong>Проверки в цикле:</strong> каждые 30 секунд</p>
            <p><strong>Остановка:</strong> после ЛЮБОГО сообщения Kiro (с семенами или без)</p>
            <p><strong>Умное время:</strong> +30 сек окно для сообщений из конца предыдущего цикла</p>
        </div>
        
        <div class="card">
            <h2>🏆 Найдено семян</h2>
            <ul>{"".join([f'<li>{item}</li>' for item in items_list]) if items_list else '<li>Еще не найдено</li>'}</ul>
        </div>
    </body>
    </html>
    """

@app.route('/status')
def status_page():
    return home()

@app.route('/health')
def health_check():
    return "OK"

@app.route('/emergency_reset')
def emergency_reset():
    """Ручной сброс аварийного режима (для админа)"""
    global discord_emergency_mode, discord_emergency_start, discord_error_count
    discord_emergency_mode = False
    discord_emergency_start = None
    discord_error_count = 0
    save_state()
    return "✅ Аварийный режим и счетчик ошибок сброшены вручную"

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    load_state()
    
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК УМНОГО МОНИТОРИНГА KIRO - ТОЛЬКО СЕМЕНА")
    logger.info("=" * 60)
    logger.info("🌱 Отслеживаю: ТОЛЬКО канал с семенами")
    logger.info("❌ НЕ отслеживаю: Ивент-шоп, Пасс-шоп")
    logger.info("🎯 Семена: 4 вида (включая тестовые томаты)")
    logger.info("🔄 5-минутные циклы (00:00, 00:05, 00:10...)")
    logger.info("⏱️ Проверка внутри цикла: каждые 30 секунд")
    logger.info("⏸️ Остановка: после ЛЮБОГО сообщения Kiro")
    logger.info("🕒 Умная проверка времени: +30 сек окно из предыдущего цикла")
    logger.info("🚨 УСИЛЕННЫЙ АВАРИЙНЫЙ РЕЖИМ: 2 ошибки → 1 ЧАС перерыва")
    logger.info("=" * 60)
    
    if discord_emergency_mode:
        logger.warning("🚨 ЗАПУСК В АВАРИЙНОМ РЕЖИМЕ! Проверка Discord приостановлена на 1 ЧАС.")
    
    # Запускаем фоновые потоки
    threads = [
        threading.Thread(target=smart_monitor, name='SeedsMonitor', daemon=True),
        threading.Thread(target=self_pinger, name='SelfPinger', daemon=True),
        threading.Thread(target=telegram_poller, name='TelegramPoller', daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Запущен поток: {thread.name}")
        time.sleep(1)
    
    # Отправляем сообщение о запуске
    emergency_alert = ""
    if discord_emergency_mode and discord_emergency_start:
        time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
        remaining = max(0, EMERGENCY_COOLDOWN - time_in_emergency)
        emergency_alert = (
            f"\n\n🚨 <b>АВАРИЙНЫЙ РЕЖИМ DISCORD АКТИВЕН (УСИЛЕННЫЙ)</b>\n"
            f"• Начало: {discord_emergency_start.strftime('%H:%M:%S')}\n"
            f"• Осталось: {remaining/60:.1f} минут\n"
            f"• Длительность: 1 ЧАС\n"
            f"• Все запросы к Discord приостановлены"
        )
    
    startup_msg = (
        "🚀 <b>УМНЫЙ МОНИТОРИНГ KIRO ЗАПУЩЕН (ТОЛЬКО СЕМЕНА)</b>\n\n"
        "🌱 <b>Отслеживаю только канал с семенами</b>\n"
        "• Ивент-шоп: ❌ НЕ отслеживается\n"
        "• Пасс-шоп: ❌ НЕ отслеживается\n\n"
        "🎯 <b>Улучшенная логика работы:</b>\n"
        "• 5-минутные циклы (00:00, 00:05, 00:10...)\n"
        "• Проверка каждые 30 секунд в цикле\n"
        "• Остановка после ЛЮБОГО сообщения Kiro\n"
        "• Умная проверка времени (+30 сек окно)\n\n"
        "🛡️ <b>УСИЛЕННЫЙ АВАРИЙНЫЙ РЕЖИМ DISCORD:</b>\n"
        f"• {MAX_ERRORS_BEFORE_EMERGENCY} ошибки подряд → 1 ЧАС перерыва\n"
        "• Автоматическое восстановление\n"
        "• Максимальная защита от блокировок\n\n"
        "🎯 <b>Отслеживаю 4 семена:</b>\n"
        "🐙 Octobloom\n"
        "🦓 Zebrazinkle\n"
        "🎆 Firework Fern\n"
        "🍅 Tomato Seeds (тестовый, частый в стоке)\n\n"
        "✅ <b>Готов к работе с максимальной защитой!</b>\n"
        "Используйте /status для проверки состояния"
        f"{emergency_alert}"
    )
    send_to_bot(startup_msg)
    
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
