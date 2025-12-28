from flask import Flask, request, jsonify
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
import re
import json
import sys

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
EVENT_SHOP_CHANNEL_ID = os.getenv('EVENT_SHOP_CHANNEL_ID')
PASS_SHOP_CHANNEL_ID = os.getenv('PASS_SHOP_CHANNEL_ID')
RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')

# Проверка переменных
REQUIRED_VARS = ['TELEGRAM_TOKEN', 'TELEGRAM_CHANNEL_ID', 'TELEGRAM_BOT_CHAT_ID', 
                 'DISCORD_TOKEN', 'SEEDS_CHANNEL_ID', 'PASS_SHOP_CHANNEL_ID']
missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
if missing:
    logger.error(f"❌ Отсутствуют переменные: {missing}")

# ==================== ОТСЛЕЖИВАЕМЫЕ ПРЕДМЕТЫ ====================
TARGET_ITEMS = {
    # 🌱 Семена (3 предмета)
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
    'firework_fern': {
        'keywords': ['firework fern', 'fireworkfern', ':fireworkfern', ':firework_fern:'],
        'sticker_id': "CAACAgIAAxkBAAEQHChpUBeOda8Uf0Uwig6BwvkW_z1ndAAC5Y0AAl8dgEoandjqAtpRWTYE",
        'emoji': '🎆',
        'display_name': 'Firework Fern',
        'channels': [SEEDS_CHANNEL_ID]
    },
    
    # 🎫 Пасс-шоп (1 предмет)
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
    PASS_SHOP_CHANNEL_ID: '🎫 Пасс-шоп'
}

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
# Ключевые переменные для защиты от дублей
last_processed_ids = {
    SEEDS_CHANNEL_ID: None,
    PASS_SHOP_CHANNEL_ID: None
}

last_processed_cycles = {
    SEEDS_CHANNEL_ID: None,
    PASS_SHOP_CHANNEL_ID: None
}

# Для хранения timestamp последних сообщений
last_message_timestamps = {
    SEEDS_CHANNEL_ID: None,
    PASS_SHOP_CHANNEL_ID: None
}

# 🔴 НОВОЕ: Аварийный режим
discord_emergency_mode = False
discord_emergency_start = None
discord_error_count = 0
discord_last_error_time = None
EMERGENCY_COOLDOWN = 1800  # 30 минут в секундах
MAX_ERRORS_BEFORE_EMERGENCY = 5  # Максимум 5 ошибок подряд
ERROR_WINDOW_SECONDS = 300  # Окно для подсчёта ошибок: 5 минут

bot_start_time = datetime.now()
bot_status = "🟢 Инициализация"
channel_enabled = True
found_items_count = {name: 0 for name in TARGET_ITEMS.keys()}
discord_request_count = 0
last_discord_request = 0
ping_count = 0
last_ping_time = None
telegram_offset = 0
last_error = None

check_lock = threading.Lock()

# Файл для сохранения состояния
STATE_FILE = 'last_ids.json'

# ==================== СОХРАНЕНИЕ СОСТОЯНИЯ ====================
def save_state():
    """Сохраняет последние ID в файл"""
    try:
        # Конвертируем datetime в строки для сохранения
        timestamps_str = {}
        for channel_id, timestamp in last_message_timestamps.items():
            if timestamp:
                timestamps_str[channel_id] = timestamp.isoformat()
            else:
                timestamps_str[channel_id] = None
        
        state = {
            'last_processed_ids': last_processed_ids,
            'last_message_timestamps': timestamps_str,
            'found_items_count': found_items_count,
            'discord_request_count': discord_request_count,
            'ping_count': ping_count,
            'discord_emergency_mode': discord_emergency_mode,
            'discord_emergency_start': discord_emergency_start.isoformat() if discord_emergency_start else None,
            'discord_error_count': discord_error_count
        }
        
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
        
        logger.debug(f"💾 Состояние сохранено")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения состояния: {e}")

def load_state():
    """Загружает последние ID из файла"""
    global last_processed_ids, found_items_count, discord_request_count, ping_count, last_message_timestamps
    global discord_emergency_mode, discord_emergency_start, discord_error_count
    
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
            
            last_processed_ids = state.get('last_processed_ids', last_processed_ids)
            found_items_count = state.get('found_items_count', found_items_count)
            discord_request_count = state.get('discord_request_count', discord_request_count)
            ping_count = state.get('ping_count', ping_count)
            
            # Загружаем timestamps
            timestamps_str = state.get('last_message_timestamps', {})
            for channel_id, timestamp_str in timestamps_str.items():
                if timestamp_str:
                    try:
                        last_message_timestamps[channel_id] = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    except:
                        last_message_timestamps[channel_id] = None
                else:
                    last_message_timestamps[channel_id] = None
            
            # Загружаем состояние аварийного режима
            discord_emergency_mode = state.get('discord_emergency_mode', False)
            emergency_start_str = state.get('discord_emergency_start')
            if emergency_start_str:
                try:
                    discord_emergency_start = datetime.fromisoformat(emergency_start_str)
                except:
                    discord_emergency_start = None
            discord_error_count = state.get('discord_error_count', 0)
            
            if discord_emergency_mode:
                logger.warning(f"🚨 Аварийный режим Discord загружен из состояния")
            
            logger.info("💾 Состояние загружено")
        else:
            logger.info("📂 Файл состояния не найден, начинаем с чистого листа")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки состояния: {e}")

# 🔴 НОВОЕ: Функции для управления аварийным режимом
def update_error_count():
    """Обновляет счётчик ошибок Discord"""
    global discord_error_count, discord_last_error_time
    
    current_time = time.time()
    
    # Если прошло больше ERROR_WINDOW_SECONDS, сбрасываем счётчик
    if discord_last_error_time and (current_time - discord_last_error_time > ERROR_WINDOW_SECONDS):
        discord_error_count = 0
        logger.info("🔄 Счётчик ошибок Discord сброшен (прошло более 5 минут)")
    
    discord_error_count += 1
    discord_last_error_time = current_time
    
    logger.warning(f"⚠️ Ошибка Discord #{discord_error_count}")
    
    # Если достигли лимита ошибок - включаем аварийный режим
    if discord_error_count >= MAX_ERRORS_BEFORE_EMERGENCY:
        activate_emergency_mode()

def activate_emergency_mode():
    """Активирует аварийный режим"""
    global discord_emergency_mode, discord_emergency_start, discord_error_count
    
    if not discord_emergency_mode:
        discord_emergency_mode = True
        discord_emergency_start = datetime.now()
        discord_error_count = 0  # Сбрасываем счётчик после активации
        
        emergency_msg = (
            f"🚨 <b>АВАРИЙНЫЙ РЕЖИМ DISCORD АКТИВИРОВАН</b>\n\n"
            f"• Причина: Слишком много ошибок Discord API\n"
            f"• Время начала: {discord_emergency_start.strftime('%H:%M:%S')}\n"
            f"• Перерыв: 30 минут\n"
            f"• Все запросы к Discord приостановлены\n"
            f"• Самопинг и команды продолжают работать\n\n"
            f"Автоматическое восстановление через 30 минут."
        )
        
        send_to_bot(emergency_msg)
        logger.error("🚨 Аварийный режим Discord активирован! Перерыв 30 минут.")
        
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
                f"• Аварийный режим длился: {time_in_emergency/60:.1f} минут\n"
                f"• Время восстановления: {datetime.now().strftime('%H:%M:%S')}\n"
                f"• Запросы к Discord возобновлены\n"
                f"• Мониторинг продолжает работу в обычном режиме"
            )
            
            send_to_bot(recovery_msg)
            logger.info("✅ Аварийный режим Discord отключён. Возобновляю работу.")
            
            save_state()
            return True
        else:
            remaining = EMERGENCY_COOLDOWN - time_in_emergency
            logger.warning(f"🚨 Аварийный режим Discord: осталось {remaining/60:.1f} минут")
            return False
    
    return True  # Если не в аварийном режиме

# ==================== TELEGRAM КОМАНДЫ ====================
def handle_telegram_command(chat_id, command, message=None):
    """Обрабатывает команды Telegram"""
    global channel_enabled
    
    logger.info(f"🎯 Обрабатываю команду: {command} от {chat_id}")
    
    if command == '/start':
        seeds_list = "\n".join([f"{config['emoji']} {config['display_name']}" 
                              for config in TARGET_ITEMS.values() if SEEDS_CHANNEL_ID in config['channels']])
        
        emergency_status = ""
        if discord_emergency_mode and discord_emergency_start:
            time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
            remaining = max(0, EMERGENCY_COOLDOWN - time_in_emergency)
            emergency_status = f"\n\n🚨 <b>АВАРИЙНЫЙ РЕЖИМ DISCORD</b>\n• Активирован: {discord_emergency_start.strftime('%H:%M:%S')}\n• Осталось: {remaining/60:.1f} минут"
        
        welcome_text = (
            "🎮 <b>Добро пожаловать в мониторинг Kiro!</b>\n\n"
            "Я отслеживаю стоки от бота Kiro в Discord и присылаю уведомления.\n\n"
            "📱 <b>Вам в личные сообщения:</b> Уведомления о найденных предметах\n"
            f"📢 <b>В канал ({TELEGRAM_CHANNEL_ID}):</b> Стикеры при обнаружении\n"
            "🏓 <b>Самопинг:</b> Активен (каждые 8 минут)\n"
            f"🛡️ <b>Аварийный режим:</b> {'🚨 АКТИВЕН' if discord_emergency_mode else '✅ ОТКЛЮЧЁН'}\n\n"
            f"🎯 <b>Отслеживаю 4 предмета:</b>\n"
            f"{seeds_list}\n"
            f"🍯 Pollen Cone (пасс-шоп)\n\n"
            "⚠️ <b>Временные изменения:</b>\n"
            "• Ивент-шоп отключен (бот Kiro временно сломан)\n"
            "• Работают: Семена (3) + Пасс-шоп (1)\n"
            f"{emergency_status}\n\n"
            "🎛️ <b>Команды:</b>\n"
            "/start - Информация\n"
            "/status - Статус бота\n" 
            "/enable - Включить канал\n"
            "/disable - Выключить канал\n"
            "/help - Помощь"
        )
        send_telegram_message(chat_id, welcome_text)
        
    elif command == '/help':
        items_list = "\n".join([f"{config['emoji']} {config['display_name']}" 
                              for name, config in TARGET_ITEMS.items()])
        
        help_text = (
            f"🤖 <b>Бот мониторинга Grow a Garden</b>\n\n"
            f"📋 <b>Доступные команды:</b>\n"
            f"/start - Начать работу\n"
            f"/status - Статус бота\n" 
            f"/enable - Включить уведомления в канал\n"
            f"/disable - Выключить уведомления в канал\n"
            f"/help - Показать это сообщение\n\n"
            f"🎯 <b>Отслеживаю 4 предмета:</b>\n"
            f"{items_list}\n\n"
            f"⚠️ <b>Временные изменения:</b>\n"
            f"• Ивент-шоп отключен\n"
            f"• Работают: Семена (3) + Пасс-шоп (1)\n\n"
            f"🛡️ <b>Аварийный режим Discord:</b>\n"
            f"• Автоматически активируется при частых ошибках\n"
            f"• Приостанавливает запросы на 30 минут\n"
            f"• Автоматически восстанавливается\n\n"
            f"🔄 Бот автоматически отслеживает стоки от Kiro и присылает уведомления."
        )
        send_telegram_message(chat_id, help_text)
        
    elif command == '/status':
        send_bot_status(chat_id)
        
    elif command == '/enable':
        channel_enabled = True
        send_telegram_message(chat_id, "✅ <b>Уведомления в канал ВКЛЮЧЕНЫ</b>\nТеперь стикеры будут приходить в канал при обнаружении предметов.")
        
    elif command == '/disable':
        channel_enabled = False
        send_telegram_message(chat_id, "⏸️ <b>Уведомления в канал ВЫКЛЮЧЕНЫ</b>\nУведомления о предметах (стикеры) временно приостановлены.")
        
    else:
        send_telegram_message(chat_id, "❌ Неизвестная команда. Используйте /help для списка команд.")

def send_bot_status(chat_id):
    """Отправляет статус бота"""
    global bot_status, last_error, channel_enabled, ping_count, last_ping_time, found_items_count
    global discord_emergency_mode, discord_emergency_start, discord_error_count
    
    uptime = datetime.now() - bot_start_time
    hours = uptime.total_seconds() / 3600
    
    last_ping_str = "Еще не было" if not last_ping_time else last_ping_time.strftime('%H:%M:%S')
    
    items_stats = "\n".join([f"{config['emoji']} {config['display_name']}: {found_items_count[name]} раз" 
                           for name, config in TARGET_ITEMS.items() if found_items_count[name] > 0])
    
    emergency_info = ""
    if discord_emergency_mode and discord_emergency_start:
        time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
        remaining = max(0, EMERGENCY_COOLDOWN - time_in_emergency)
        emergency_info = (
            f"\n\n🚨 <b>АВАРИЙНЫЙ РЕЖИМ DISCORD</b>\n"
            f"• Статус: 🚨 АКТИВЕН\n"
            f"• Активирован: {discord_emergency_start.strftime('%H:%M:%S')}\n"
            f"• Прошло: {time_in_emergency/60:.1f} минут\n"
            f"• Осталось: {remaining/60:.1f} минут\n"
            f"• Ошибок до активации: {discord_error_count}"
        )
    else:
        emergency_info = f"\n\n🛡️ <b>Аварийный режим Discord:</b> ✅ ОТКЛЮЧЁН"
    
    status_text = (
        f"📊 <b>Статус бота Kiro</b>\n\n"
        f"{bot_status}\n"
        f"⏰ Время работы: {hours:.1f} часов\n"
        f"📅 Запущен: {bot_start_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"🔄 Отслеживаю: Семена (3) + Пасс-шоп (1)\n"
        f"🏓 Самопинг: {ping_count} раз (последний: {last_ping_str})\n"
        f"💾 Запросов к Discord: {discord_request_count}\n"
        f"📝 Последние ID: {last_processed_ids}\n"
        f"🕒 Последние timestamps: {last_message_timestamps}{emergency_info}\n\n"
        f"🎯 <b>Найдено предметов:</b>\n"
        f"{items_stats if items_stats else 'Еще не найдено'}\n\n"
        f"⚠️ <b>Временные изменения:</b>\n"
        f"• Ивент-шоп отключен\n"
        f"• Работают: Семена (3) + Пасс-шоп (1)"
    )
    
    if last_error:
        status_text += f"\n\n⚠️ <b>Последняя ошибка:</b>\n<code>{last_error}</code>"
    
    send_telegram_message(chat_id, status_text)

def telegram_poller():
    """Опросщик Telegram команд"""
    global telegram_offset
    
    logger.info("🔍 Запускаю Telegram поллер...")
    
    time.sleep(10)
    telegram_offset = 0
    
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

# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML", disable_notification=False):
    """Отправляет сообщение в Telegram"""
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены Telegram переменные")
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

def send_telegram_sticker_with_retry(chat_id, sticker_id, max_retries=2):
    """Отправка стикера с повторными попытками"""
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены Telegram переменные")
        return False
    
    for attempt in range(max_retries):
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
            data = {
                "chat_id": chat_id,
                "sticker": sticker_id,
                "disable_notification": True
            }
            
            response = requests.post(url, json=data, timeout=15)
            
            if response.status_code == 200:
                return True
            elif response.status_code == 429:
                retry_after = response.json().get('parameters', {}).get('retry_after', 30)
                logger.warning(f"⚠️ Лимит Telegram, жду {retry_after} сек")
                time.sleep(retry_after)
                continue
            else:
                logger.error(f"❌ Ошибка отправки стикера {response.status_code}")
                time.sleep(2)
                continue
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки стикера (попытка {attempt+1}): {e}")
            time.sleep(1)
    
    return False

def send_to_channel(sticker_id=None, text=None):
    """Отправка в канал с защитой от спама"""
    if not channel_enabled or not TELEGRAM_CHANNEL_ID:
        logger.debug("⏸️ Канал отключен")
        return False
    
    if not hasattr(send_to_channel, 'last_send_time'):
        send_to_channel.last_send_time = 0
    
    current_time = time.time()
    time_since_last = current_time - send_to_channel.last_send_time
    
    if time_since_last < 3:
        wait_time = 3 - time_since_last
        logger.debug(f"⏸️ Защита от спама: жду {wait_time:.1f} сек")
        time.sleep(wait_time)
    
    send_to_channel.last_send_time = time.time()
    
    if sticker_id:
        return send_telegram_sticker_with_retry(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    
    return False

def send_to_bot(text, disable_notification=False):
    """Отправляет сообщение в ТЕЛЕГРАМ БОТА"""
    if not TELEGRAM_BOT_CHAT_ID:
        return False
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text, disable_notification=disable_notification)

# 🔴 ОБНОВЛЁННАЯ ФУНКЦИЯ: Добавлена проверка аварийного режима
def safe_fetch_discord_messages(channel_id, limit=2, max_retries=1):
    """Устойчивый запрос к Discord API"""
    global discord_request_count, last_discord_request, last_error
    
    # 🔴 Проверяем аварийный режим
    if not check_emergency_mode():
        logger.warning("⏸️ Аварийный режим Discord активен - пропускаем запрос")
        return None
    
    if not DISCORD_TOKEN or not channel_id:
        logger.warning(f"⚠️ Нет токена или ID канала")
        return None
    
    for attempt in range(max_retries):
        try:
            current_time = time.time()
            time_since_last = current_time - last_discord_request
            
            # Увеличиваем минимальную задержку до 20 секунд
            if time_since_last < 20:
                wait_time = 20 - time_since_last
                logger.debug(f"⏳ Защита от лимита Discord: жду {wait_time:.1f} сек")
                time.sleep(wait_time)
            
            discord_request_count += 1
            last_discord_request = time.time()
            
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
            headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                if not response.text or response.text.strip() == '':
                    logger.warning(f"⚠️ Discord вернул пустой ответ")
                    time.sleep(2)
                    continue
                
                messages = response.json()
                kiro_messages = []
                
                for msg in messages:
                    author = msg.get('author', {})
                    username = author.get('username', '').lower()
                    is_bot = author.get('bot', False)
                    
                    if ('kiro' in username) or (is_bot and 'kiro' in username):
                        kiro_messages.append(msg)
                
                if attempt > 0:
                    logger.info(f"✅ Успешный запрос к Discord после {attempt+1} попыток")
                
                last_error = None
                return kiro_messages
                
            elif response.status_code == 429:
                retry_after = response.json().get('retry_after', 5.0)
                last_error = f"Discord лимит: {retry_after} сек"
                logger.warning(f"⏳ Discord API лимит. Жду {retry_after} сек.")
                
                # 🔴 Обновляем счётчик ошибок
                update_error_count()
                
                # Ждём на 2 секунды больше, чем просит Discord
                total_wait = retry_after + 2.0
                time.sleep(total_wait)
                continue
            else:
                last_error = f"Discord API ошибка: {response.status_code}"
                logger.error(f"❌ Ошибка Discord API {response.status_code}")
                
                # 🔴 Обновляем счётчик ошибок
                update_error_count()
                
                time.sleep(5)
                continue
                
        except requests.exceptions.Timeout:
            last_error = "Таймаут Discord"
            logger.warning(f"⏰ Таймаут запроса к Discord (попытка {attempt+1}/{max_retries})")
            
            # 🔴 Обновляем счётчик ошибок
            update_error_count()
            
            if attempt < max_retries - 1:
                time.sleep(3)
            continue
        except Exception as e:
            last_error = f"Ошибка Discord: {e}"
            logger.error(f"❌ Ошибка Discord: {e}")
            
            # 🔴 Обновляем счётчик ошибок
            update_error_count()
            
            time.sleep(3)
            continue
    
    logger.error(f"❌ Не удалось получить сообщения от Discord")
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

def get_current_cycle(channel_id):
    """Возвращает текущий цикл для канала"""
    now = datetime.now()
    
    if channel_id == SEEDS_CHANNEL_ID:
        cycle_minute = (now.minute // 5) * 5
        return f"{now.hour:02d}{cycle_minute:02d}"
    
    elif channel_id == PASS_SHOP_CHANNEL_ID:
        cycle_minute = (now.minute // 5) * 5
        return f"{now.hour:02d}{cycle_minute:02d}"
    
    return None

def get_cycle_start_time(channel_id):
    """Возвращает datetime начала текущего цикл"""
    now = datetime.now()
    
    if channel_id == SEEDS_CHANNEL_ID:
        # Семена: 5-минутные циклы (00:00, 00:05, 00:10...)
        minute = now.minute
        cycle_minute = (minute // 5) * 5
        return now.replace(minute=cycle_minute, second=0, microsecond=0)
    
    elif channel_id == PASS_SHOP_CHANNEL_ID:
        # Пасс-шоп: 5-минутные циклы (00:00, 00:05, 00:10...)
        minute = now.minute
        cycle_minute = (minute // 5) * 5
        return now.replace(minute=cycle_minute, second=0, microsecond=0)
    
    return now

def parse_discord_timestamp(timestamp_str):
    """Парсит Discord timestamp без dateutil"""
    try:
        # Формат: "2023-12-26T00:00:00.000Z"
        if not timestamp_str:
            return None
        
        # Убираем миллисекунды и 'Z'
        clean_str = timestamp_str
        
        # Убираем .000 (миллисекунды)
        if '.' in clean_str:
            clean_str = clean_str.split('.')[0]
        
        # Заменяем Z на +00:00 для fromisoformat
        if clean_str.endswith('Z'):
            clean_str = clean_str[:-1] + '+00:00'
        
        return datetime.fromisoformat(clean_str)
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга timestamp '{timestamp_str}': {e}")
        return None

def is_message_for_current_cycle(message, channel_id):
    """Проверяет, относится ли сообщение к текущему циклу"""
    try:
        timestamp_str = message.get('timestamp')
        if not timestamp_str:
            logger.warning("⚠️ Сообщение без timestamp")
            return True  # На всякий случай обрабатываем
        
        message_time = parse_discord_timestamp(timestamp_str)
        if not message_time:
            logger.warning("⚠️ Не удалось распарсить timestamp")
            return True  # На всякий случай обрабатываем
        
        cycle_start = get_cycle_start_time(channel_id)
        
        # Сообщение относится к текущему циклу, если оно создано ПОСЛЕ начала цикла
        is_for_current_cycle = message_time >= cycle_start
        
        if not is_for_current_cycle:
            logger.debug(f"⏪ Сообщение от {message_time} слишком старое (цикл начался {cycle_start})")
        
        return is_for_current_cycle
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки timestamp: {e}")
        return True  # В случае ошибки обрабатываем сообщение

def should_check_channel_now(channel_id):
    """Определяет, нужно ли проверять канал сейчас"""
    # 🔴 Проверяем аварийный режим
    if not check_emergency_mode():
        return False
    
    current_cycle = get_current_cycle(channel_id)
    
    if last_processed_cycles.get(channel_id) == current_cycle:
        logger.debug(f"⏭️ Пропускаем - уже обрабатывали цикл {current_cycle}")
        return False
    
    if channel_id == SEEDS_CHANNEL_ID:
        if not hasattr(should_check_channel_now, 'last_seeds_check'):
            should_check_channel_now.last_seeds_check = 0
        
        current_time = time.time()
        if current_time - should_check_channel_now.last_seeds_check < 60:  # Увеличили до 60 секунд
            return False
        
        should_check_channel_now.last_seeds_check = current_time
        return True
    
    elif channel_id == PASS_SHOP_CHANNEL_ID:
        now = datetime.now()
        minute_in_cycle = now.minute % 5
        second = now.second
        
        if minute_in_cycle == 0 and second == 40:
            return True
        if minute_in_cycle == 1 and second == 10:
            return True
        
        return False
    
    return False

def check_channel(channel_id):
    """Проверяет один канал Discord с защитой от дублей"""
    global last_processed_ids, last_processed_cycles, found_items_count, bot_status, last_message_timestamps
    
    # 🔴 Проверяем аварийный режим
    if not check_emergency_mode():
        return False
    
    channel_name = CHANNEL_NAMES.get(channel_id, channel_id)
    current_cycle = get_current_cycle(channel_id)
    
    if last_processed_cycles.get(channel_id) == current_cycle:
        logger.debug(f"⏭️ Пропускаем {channel_name} - уже обрабатывали цикл {current_cycle}")
        return False
    
    messages = safe_fetch_discord_messages(channel_id, limit=2)
    if not messages:
        logger.debug(f"📭 В {channel_name} нет сообщений от Kiro")
        return False
    
    found_items_in_this_check = []
    found_new_message = False
    
    for message in messages:
        message_id = message['id']
        
        # Проверяем timestamp сообщения
        if not is_message_for_current_cycle(message, channel_id):
            logger.debug(f"⏪ Игнорируем старое сообщение в {channel_name}")
            continue  # Пропускаем сообщения из предыдущих циклов
        
        # Сохраняем timestamp сообщения
        try:
            timestamp_str = message.get('timestamp')
            if timestamp_str:
                message_time = parse_discord_timestamp(timestamp_str)
                if message_time:
                    last_message_timestamps[channel_id] = message_time
        except Exception as e:
            logger.error(f"❌ Ошибка получения timestamp: {e}")
        
        # Проверка по ID (старая логика)
        last_id = last_processed_ids.get(channel_id)
        if last_id and int(message_id) <= int(last_id):
            continue
        
        # НОВОЕ сообщение!
        found_new_message = True
        last_processed_ids[channel_id] = message_id
        
        text = extract_text_from_message(message)
        
        for item_name, item_config in TARGET_ITEMS.items():
            if channel_id not in item_config['channels']:
                continue
            
            for keyword in item_config['keywords']:
                if keyword.lower() in text:
                    cycle_key = f"{channel_id}_{current_cycle}_{item_name}"
                    
                    if cycle_key not in found_items_in_this_check:
                        found_items_count[item_name] += 1
                        found_items_in_this_check.append((cycle_key, item_config))
                    break
        
        break
    
    if not found_new_message:
        return False
    
    if found_items_in_this_check:
        logger.info(f"🎯 Найдены предметы в {channel_name}: {len(found_items_in_this_check)} шт")
        
        for cycle_key, item_config in found_items_in_this_check:
            current_time_str = datetime.now().strftime('%H:%M:%S')
            notification = f"✅ Найден {item_config['emoji']} {item_config['display_name']} в {current_time_str}"
            
            success = send_to_bot(notification, disable_notification=False)
            if success:
                logger.info(f"📱 Уведомление отправлено: {item_config['display_name']}")
            else:
                logger.error(f"❌ Не удалось отправить уведомление о {item_config['display_name']}")
            
            if send_to_channel(sticker_id=item_config['sticker_id']):
                logger.info(f"✅ Стикер {item_config['emoji']} отправлен в канал")
            else:
                logger.error(f"❌ Ошибка отправки стикера {item_config['emoji']}")
        
        last_processed_cycles[channel_id] = current_cycle
        bot_status = f"🟢 Найдены предметы в {channel_name}"
        
        save_state()
        return True
    
    last_processed_cycles[channel_id] = current_cycle
    logger.info(f"📭 Kiro в {channel_name} без нужных предметов")
    bot_status = f"🟢 Проверен {channel_name}"
    
    save_state()
    return False

# ==================== МОНИТОРЫ ====================
def monitor_seeds():
    """Мониторинг семян (каждые 60 секунд)"""
    logger.info("🌱 Запуск мониторинга семян (каждые 60 секунд)")
    
    while True:
        try:
            if should_check_channel_now(SEEDS_CHANNEL_ID):
                with check_lock:
                    check_channel(SEEDS_CHANNEL_ID)
            
            time.sleep(60)  # Увеличили до 60 секунд
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторинге семян: {e}")
            time.sleep(10)

def monitor_pass_shop():
    """Мониторинг пасс-шопа (по расписанию)"""
    logger.info("🎫 Запуск мониторинга пасс-шопа (по расписанию)")
    
    while True:
        try:
            if should_check_channel_now(PASS_SHOP_CHANNEL_ID):
                with check_lock:
                    check_channel(PASS_SHOP_CHANNEL_ID)
            
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторинге пасс-шопа: {e}")
            time.sleep(10)

# Временная функция (отключена)
def monitor_event_shop():
    """Временно отключено"""
    logger.info("🎪 Мониторинг ивент-шопа временно отключен")
    while True:
        time.sleep(3600)

def self_pinger():
    """Самопинг чтобы Render не останавливал сервис"""
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
                logger.info("✅ Самопинг успешен - сервис активен")
            else:
                logger.warning(f"⚠️ Самопинг: статус {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
        
        logger.info("💤 Ожидаю 8 минут до следующего самопинга...")
        time.sleep(480)

def health_monitor():
    """Отправляет статус каждые 6 часов"""
    logger.info("📊 Монитор здоровья запущен (каждые 6 часов)")
    
    time.sleep(60)
    
    report_count = 0
    
    while True:
        try:
            time.sleep(6 * 60 * 60)
            
            report_count += 1
            uptime = datetime.now() - bot_start_time
            uptime_hours = uptime.total_seconds() / 3600
            
            items_stats = []
            for item_name, count in found_items_count.items():
                if count > 0:
                    item = TARGET_ITEMS[item_name]
                    items_stats.append(f"{item['emoji']} {item['display_name']}: {count}")
            
            stats_text = "\n".join(items_stats) if items_stats else "Еще не найдено"
            
            emergency_info = ""
            if discord_emergency_mode and discord_emergency_start:
                time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
                remaining = max(0, EMERGENCY_COOLDOWN - time_in_emergency)
                emergency_info = (
                    f"\n\n🚨 <b>АВАРИЙНЫЙ РЕЖИМ DISCORD</b>\n"
                    f"• Статус: 🚨 АКТИВЕН\n"
                    f"• Активирован: {discord_emergency_start.strftime('%H:%M:%S')}\n"
                    f"• Осталось: {remaining/60:.1f} минут"
                )
            
            status_msg = (
                f"📊 <b>АВТО-СТАТУС #{report_count}</b>\n"
                f"⏰ Работает: {uptime_hours:.1f} часов\n"
                f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
                f"🔄 {bot_status}\n"
                f"🏓 Самопинг: {ping_count} раз\n"
                f"💾 Запросов к Discord: {discord_request_count}\n"
                f"📝 Последние ID: {last_processed_ids}\n"
                f"🕒 Последние timestamps: {last_message_timestamps}{emergency_info}\n\n"
                f"🎯 <b>Найдено предметов:</b>\n"
                f"{stats_text}\n\n"
                f"⚠️ <b>Временные изменения:</b>\n"
                f"• Ивент-шоп отключен\n"
                f"• Работают: Семена (3) + Пасс-шоп (1)\n\n"
                f"✅ Бот стабильно работает"
            )
            
            send_to_bot(status_msg)
            logger.info(f"📊 Авто-статус #{report_count} отправлен в бота")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки авто-статуса: {e}")

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
        current_cycle = get_current_cycle(channel_id)
        last_cycle = last_processed_cycles.get(channel_id)
        status = "🟢 Активен" if last_cycle != current_cycle else "⏸️ Обработан"
        cycles_status.append(f"{channel_name}: {status} (цикл: {current_cycle})")
    
    tracked_items = []
    for item in TARGET_ITEMS.values():
        channels_str = ""
        if SEEDS_CHANNEL_ID in item['channels']:
            channels_str += "🌱 "
        if PASS_SHOP_CHANNEL_ID in item['channels']:
            channels_str += "🎫 "
        tracked_items.append(f"{item['emoji']} {item['display_name']} → {channels_str}")
    
    emergency_info = ""
    if discord_emergency_mode and discord_emergency_start:
        time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
        remaining = max(0, EMERGENCY_COOLDOWN - time_in_emergency)
        emergency_info = f"""
        <div class="card" style="background: #ffcccc;">
            <h2>🚨 АВАРИЙНЫЙ РЕЖИМ DISCORD</h2>
            <p><strong>Статус:</strong> 🚨 АКТИВЕН</p>
            <p><strong>Активирован:</strong> {discord_emergency_start.strftime('%H:%M:%S')}</p>
            <p><strong>Прошло:</strong> {time_in_emergency/60:.1f} минут</p>
            <p><strong>Осталось:</strong> {remaining/60:.1f} минут</p>
            <p><strong>Все запросы к Discord приостановлены</strong></p>
        </div>
        """
    
    return f"""
    <html>
    <head>
        <title>🌱 Мониторинг Kiro (4 предмета)</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .card {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .status-ok {{ color: #2ecc71; }}
            .status-emergency {{ color: #e74c3c; }}
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
        <h1>🌱 Мониторинг Kiro (4 предмета)</h1>
        
        {emergency_info}
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> <span class="status-ok">{bot_status}</span></p>
            <p><strong>Время работы:</strong> {uptime_str}</p>
            <p><strong>Запросов к Discord:</strong> {discord_request_count}</p>
            <p><strong>Самопингов:</strong> {ping_count}</p>
            <p><strong>Аварийный режим:</strong> <span class="{'status-emergency' if discord_emergency_mode else 'status-ok'}">{'🚨 АКТИВЕН' if discord_emergency_mode else '✅ ОТКЛЮЧЁН'}</span></p>
            <p><strong>Последние ID:</strong> {last_processed_ids}</p>
            <p><strong>Последние timestamps:</strong> {last_message_timestamps}</p>
        </div>
        
        <div class="card">
            <h2>⚠️ Временные изменения</h2>
            <p><strong>Ивент-шоп отключен</strong> (бот Kiro временно сломан)</p>
            <p><strong>Работают: Семена (3) + Пасс-шоп (1)</strong></p>
        </div>
        
        <div class="card">
            <h2>🔄 Состояние циклов</h2>
            <ul>{"".join([f'<li>{status}</li>' for status in cycles_status])}</ul>
        </div>
        
        <div class="card">
            <h2>🎛️ Управление через Telegram</h2>
            <p><strong>Доступные команды:</strong></p>
            <ul>
                <li><code>/start</code> - Информация о боте</li>
                <li><code>/status</code> - Текущий статус</li>
                <li><code>/enable</code> - Включить канал</li>
                <li><code>/disable</code> - Выключить канал</li>
                <li><code>/help</code> - Помощь</li>
            </ul>
            <p><strong>Напишите боту в Telegram для управления!</strong></p>
        </div>
        
        <div class="card">
            <h2>🎯 Отслеживаемые предметы (4 предмета)</h2>
            <ul>{"".join([f'<li>{item}</li>' for item in tracked_items])}</ul>
        </div>
        
        <div class="card">
            <h2>🎯 Стратегия мониторинга</h2>
            <p><strong>🌱 Семена (3 предмета):</strong> Каждые 60 секунд + защита от старых сообщений</p>
            <p><strong>🎫 Пасс-шоп (1 предмет):</strong> По расписанию (:40, 1:10) + защита от старых сообщений</p>
            <p><strong>🎪 Ивент-шоп:</strong> Временно отключен</p>
            <p><strong>🛡️ Аварийный режим:</strong> Активируется при 5 ошибках Discord за 5 минут</p>
        </div>
        
        <div class="card">
            <h2>🏆 Найдено предметов</h2>
            <ul>{"".join([f'<li>{item}</li>' for item in found_items]) if found_items else '<li>Еще не найдено</li>'}</ul>
        </div>
    </body>
    </html>
    """

@app.route('/enable')
def enable_channel():
    global channel_enabled
    channel_enabled = True
    return "✅ Отправка стикеров в канал включена"

@app.route('/disable')
def disable_channel():
    global channel_enabled
    channel_enabled = False
    return "⏸️ Отправка стикеров в канал выключена"

@app.route('/status')
def status_page():
    return home()

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': (datetime.now() - bot_start_time).total_seconds(),
        'discord_requests': discord_request_count,
        'channel_enabled': channel_enabled,
        'ping_count': ping_count,
        'discord_emergency_mode': discord_emergency_mode,
        'discord_emergency_start': discord_emergency_start.isoformat() if discord_emergency_start else None,
        'discord_error_count': discord_error_count,
        'last_processed_ids': last_processed_ids,
        'last_message_timestamps': {k: (v.isoformat() if v else None) for k, v in last_message_timestamps.items()},
        'found_items_total': sum(found_items_count.values())
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    load_state()
    
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК МОНИТОРИНГА KIRO С АВАРИЙНЫМ РЕЖИМОМ")
    logger.info("=" * 60)
    logger.info("🎯 Отслеживаю 4 предмета:")
    logger.info("   🌱 3 семена: Octobloom, Zebrazinkle, Firework Fern")
    logger.info("   🎫 1 пасс-шоп: Pollen Cone")
    logger.info("⚠️ Ивент-шоп отключен (бот Kiro временно сломан)")
    logger.info("🌱 Семена: каждые 60 сек + защита от старых сообщений")
    logger.info("🎫 Пасс-шоп: по расписанию (:40, 1:10) + защита от старых сообщений")
    logger.info("🛡️ Аварийный режим Discord: 5 ошибок за 5 мин → перерыв 30 мин")
    logger.info("🏓 Самопинг: каждые 8 минут")
    logger.info("📊 Авто-статус: каждые 6 часов")
    logger.info("💾 Сохранение состояния: включено (ID + timestamps + emergency)")
    logger.info("=" * 60)
    
    if discord_emergency_mode:
        logger.warning("🚨 ЗАПУСК В АВАРИЙНОМ РЕЖИМЕ! Проверка Discord приостановлена.")
    
    threads = [
        threading.Thread(target=monitor_seeds, name='SeedsMonitor', daemon=True),
        threading.Thread(target=monitor_pass_shop, name='PassShopMonitor', daemon=True),
        threading.Thread(target=monitor_event_shop, name='EventShopMonitor', daemon=True),
        threading.Thread(target=self_pinger, name='SelfPinger', daemon=True),
        threading.Thread(target=health_monitor, name='HealthMonitor', daemon=True),
        threading.Thread(target=telegram_poller, name='TelegramPoller', daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Запущен поток: {thread.name}")
        time.sleep(1)
    
    seeds_list = "\n".join([f"{config['emoji']} {config['display_name']}" 
                          for config in TARGET_ITEMS.values() if SEEDS_CHANNEL_ID in config['channels']])
    
    emergency_alert = ""
    if discord_emergency_mode and discord_emergency_start:
        time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
        remaining = max(0, EMERGENCY_COOLDOWN - time_in_emergency)
        emergency_alert = (
            f"\n\n🚨 <b>АВАРИЙНЫЙ РЕЖИМ DISCORD АКТИВЕН</b>\n"
            f"• Причина: Слишком много ошибок Discord API\n"
            f"• Время начала: {discord_emergency_start.strftime('%H:%M:%S')}\n"
            f"• Прошло: {time_in_emergency/60:.1f} минут\n"
            f"• Осталось: {remaining/60:.1f} минут\n"
            f"• Все запросы к Discord приостановлены\n"
            f"• Автоматическое восстановление через {remaining/60:.1f} минут"
        )
    
    startup_msg = (
        "🚀 <b>МОНИТОРИНГ KIRO ЗАПУЩЕН С АВАРИЙНЫМ РЕЖИМОМ</b>\n\n"
        f"🎯 <b>Отслеживаю 4 предмета:</b>\n"
        f"{seeds_list}\n"
        f"🍯 Pollen Cone (пасс-шоп)\n\n"
        "⚠️ <b>Временные изменения:</b>\n"
        "• Ивент-шоп отключен (бот Kiro временно сломан)\n"
        "• Работают: Семена (3) + Пасс-шоп (1)"
        f"{emergency_alert}\n\n"
        "🕐 <b>Расписание проверок:</b>\n"
        "🌱 Семена: каждые 60 сек (мин. 60 сек между проверками)\n"
        "🎫 Пасс-шоп: :40 и 1:10 каждые 5 минут\n\n"
        "🛡️ <b>НОВАЯ СИСТЕМА АВАРИЙНОГО РЕЖИМА:</b>\n"
        "• 5 ошибок Discord за 5 минут → перерыв 30 минут\n"
        "• Все запросы к Discord автоматически приостанавливаются\n"
        "• Автоматическое восстановление через 30 минут\n"
        "• Уведомления в Telegram при активации/восстановлении\n\n"
        "💾 <b>Сохранение состояния:</b> Включено (ID + timestamps + emergency)\n"
        "🏓 <b>Самопинг:</b> Активен (каждые 8 минут)\n"
        "📊 <b>Авто-статус:</b> Каждые 6 часов\n\n"
        "🎛️ <b>Команды управления:</b>\n"
        "/start - Информация\n"
        "/status - Статус бота\n" 
        "/enable - Включить канал\n"
        "/disable - Выключить канал\n"
        "/help - Помощь\n\n"
        "✅ <b>Готов к работе! Начинаю мониторинг...</b>"
    )
    send_to_bot(startup_msg)
    
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
