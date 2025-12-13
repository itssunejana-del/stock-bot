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
EGGS_CHANNEL_ID = os.getenv('EGGS_CHANNEL_ID')
PASS_SHOP_CHANNEL_ID = os.getenv('PASS_SHOP_CHANNEL_ID')
RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')

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

last_processed_cycles = {
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
ping_count = 0
last_ping_time = None
telegram_offset = 0
last_error = None

STATE_FILE = 'bot_state.json'

# ==================== TELEGRAM КОМАНДЫ ====================
def handle_telegram_command(chat_id, command, message=None):
    """Обрабатывает команды Telegram (как в Ember боте)"""
    global channel_enabled
    
    logger.info(f"🎯 Обрабатываю команду: {command} от {chat_id}")
    
    if command == '/start':
        seeds_list = "\n".join([f"{config['emoji']} {config['display_name']}" 
                              for config in TARGET_ITEMS.values() if SEEDS_CHANNEL_ID in config['channels']])
        
        welcome_text = (
            "🎮 <b>Добро пожаловать в мониторинг Kiro!</b>\n\n"
            "Я отслеживаю стоки от бота Kiro в Discord и присылаю уведомления.\n\n"
            "📱 <b>Вам в личные сообщения:</b> Уведомления о найденных предметах\n"
            "📢 <b>В канал:</b> Стикеры при обнаружении\n"
            "🏓 <b>Самопинг:</b> Активен (каждые 8 минут)\n\n"
            f"🎯 <b>Отслеживаю:</b>\n"
            f"{seeds_list}\n\n"
            "🎛️ <b>Команды:</b>\n"
            "/start - Информация\n"
            "/status - Статус бота\n" 
            "/enable - Включить канал\n"
            "/disable - Выключить канал\n"
            "/help - Помощь"
        )
        send_telegram_message(chat_id, welcome_text)
        
    elif command == '/help':
        seeds_list = "\n".join([f"{config['emoji']} {config['display_name']}" 
                              for name, config in TARGET_ITEMS.items()])
        
        help_text = (
            f"🤖 <b>Бот мониторинга Grow a Garden</b>\n\n"
            f"📋 <b>Доступные команды:</b>\n"
            f"/start - Начать работу\n"
            f"/status - Статус бота\n" 
            f"/enable - Включить уведомления в канал\n"
            f"/disable - Выключить уведомления в канал\n"
            f"/help - Показать это сообщение\n\n"
            f"🎯 <b>Отслеживаю предметы:</b>\n"
            f"{seeds_list}\n\n"
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
    
    uptime = datetime.now() - bot_start_time
    hours = uptime.total_seconds() / 3600
    
    last_ping_str = "Еще не было" if not last_ping_time else last_ping_time.strftime('%H:%M:%S')
    
    seeds_stats = "\n".join([f"{config['emoji']} {config['display_name']}: {found_items_count[name]} раз" 
                           for name, config in TARGET_ITEMS.items() if found_items_count[name] > 0])
    
    status_text = (
        f"📊 <b>Статус бота Kiro</b>\n\n"
        f"{bot_status}\n"
        f"⏰ Время работы: {hours:.1f} часов\n"
        f"📅 Запущен: {bot_start_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"🔄 Отслеживаю: Kiro bot (3 канала)\n"
        f"🏓 Самопинг: {ping_count} раз (последний: {last_ping_str})\n"
        f"💾 Запросов к Discord: {discord_request_count}\n"
        f"📝 В памяти: {len(processed_messages_cache)} сообщений\n\n"
        f"🎯 <b>Найдено предметов:</b>\n"
        f"{seeds_stats if seeds_stats else 'Еще не найдено'}"
    )
    
    if last_error:
        status_text += f"\n\n⚠️ <b>Последняя ошибка:</b>\n<code>{last_error}</code>"
    
    send_telegram_message(chat_id, status_text)

def telegram_poller():
    """Опросщик Telegram команд (как в Ember боте)"""
    global telegram_offset
    
    logger.info("🔍 Запускаю Telegram поллер...")
    
    # Ждем немного чтобы избежать конфликта при старте
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
                                handle_telegram_command(chat_id, text)
                
                # Увеличиваем паузу между запросами
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
    
    # Защита от спама (3 секунды между сообщениями)
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

def safe_fetch_discord_messages(channel_id, limit=2, max_retries=2):
    """Устойчивый запрос к Discord API"""
    global discord_request_count, last_discord_request, last_error
    
    if not DISCORD_TOKEN or not channel_id:
        logger.warning(f"⚠️ Нет токена или ID канала для {CHANNEL_NAMES.get(channel_id, channel_id)}")
        return None
    
    for attempt in range(max_retries):
        try:
            # Защита от частых запросов (8 секунд)
            current_time = time.time()
            time_since_last = current_time - last_discord_request
            
            if time_since_last < 8:
                wait_time = 8 - time_since_last
                logger.debug(f"⏳ Защита от лимита Discord: жду {wait_time:.1f} сек")
                time.sleep(wait_time)
            
            discord_request_count += 1
            last_discord_request = time.time()
            
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
            headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                if not response.text or response.text.strip() == '':
                    logger.warning(f"⚠️ Discord вернул пустой ответ для {CHANNEL_NAMES.get(channel_id, channel_id)}")
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
                time.sleep(retry_after)
                continue
            else:
                last_error = f"Discord API ошибка: {response.status_code}"
                logger.error(f"❌ Ошибка Discord API {response.status_code}")
                time.sleep(5)
                continue
                
        except requests.exceptions.Timeout:
            last_error = "Таймаут Discord"
            logger.warning(f"⏰ Таймаут запроса к Discord (попытка {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(3)
            continue
        except Exception as e:
            last_error = f"Ошибка Discord: {e}"
            logger.error(f"❌ Ошибка Discord: {e}")
            time.sleep(3)
            continue
    
    logger.error(f"❌ Не удалось получить сообщения от Discord для {CHANNEL_NAMES.get(channel_id, channel_id)}")
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
        # 5-минутные циклы для семян (00, 05, 10, ...)
        cycle_minute = (now.minute // 5) * 5
        return f"{now.hour:02d}{cycle_minute:02d}"
    
    elif channel_id == EGGS_CHANNEL_ID:
        # 30-минутные циклы для яиц (00, 30)
        if now.minute < 30:
            cycle_minute = 0
        else:
            cycle_minute = 30
        return f"{now.hour:02d}{cycle_minute:02d}"
    
    elif channel_id == PASS_SHOP_CHANNEL_ID:
        # 5-минутные циклы для пасс-шопа (00, 05, 10, ...)
        cycle_minute = (now.minute // 5) * 5
        return f"{now.hour:02d}{cycle_minute:02d}"
    
    return None

def should_check_channel_now(channel_id):
    """Определяет, нужно ли проверять канал сейчас"""
    current_cycle = get_current_cycle(channel_id)
    
    # Если уже обрабатывали этот цикл - не проверяем
    if last_processed_cycles.get(channel_id) == current_cycle:
        return False
    
    now = datetime.now()
    
    # Для семян: проверяем всегда (будет фильтр по циклу выше)
    if channel_id == SEEDS_CHANNEL_ID:
        return True
    
    # Для яиц: проверяем только в 00 и 30 минут
    elif channel_id == EGGS_CHANNEL_ID:
        if now.minute not in [0, 30]:
            return False
        
        # Внутри 30-минутного цикла проверяем 3 раза
        minute_in_cycle = now.minute % 30  # 0 или 30, но после % будет 0
        second = now.second
        
        # Проверки через 30 сек, 2 мин и 5 мин после начала цикла
        if minute_in_cycle == 0 and second == 30:  # 00:30 или 30:30
            return True
        if minute_in_cycle == 2 and second == 0:   # 02:00 или 32:00
            return True
        if minute_in_cycle == 5 and second == 0:   # 05:00 или 35:00
            return True
        
        return False
    
    # Для пасс-шопа: проверяем каждые 5 минут
    elif channel_id == PASS_SHOP_CHANNEL_ID:
        minute_in_cycle = now.minute % 5
        second = now.second
        
        # Проверки через 40 сек и 1 мин 10 сек после начала цикла
        if minute_in_cycle == 0 and second == 40:   # :00:40, :05:40, ...
            return True
        if minute_in_cycle == 1 and second == 10:   # :01:10, :06:10, ...
            return True
        
        return False
    
    return False

def check_channel(channel_id):
    """Проверяет один канал Discord"""
    global last_processed_ids, last_processed_cycles, found_items_count, bot_status
    
    channel_name = CHANNEL_NAMES.get(channel_id, channel_id)
    current_cycle = get_current_cycle(channel_id)
    
    # Получаем сообщения
    messages = safe_fetch_discord_messages(channel_id, limit=2)
    if not messages:
        logger.debug(f"📭 В {channel_name} нет сообщений от Kiro")
        return False
    
    found_items_in_this_check = []
    
    for message in messages:
        message_id = message['id']
        
        # Пропускаем уже обработанные сообщения
        if message_id in processed_messages_cache:
            continue
        
        # Пропускаем старые сообщения
        last_id = last_processed_ids.get(channel_id)
        if last_id and int(message_id) <= int(last_id):
            continue
        
        # Нашли новое сообщение от Kiro!
        processed_messages_cache.add(message_id)
        last_processed_ids[channel_id] = message_id
        
        # Извлекаем текст
        text = extract_text_from_message(message)
        
        # Ищем предметы для этого канала
        for item_name, item_config in TARGET_ITEMS.items():
            if channel_id not in item_config['channels']:
                continue
            
            for keyword in item_config['keywords']:
                if keyword.lower() in text:
                    # Защита от дублей в этом цикле
                    cycle_key = f"{channel_id}_{current_cycle}_{item_name}"
                    
                    if cycle_key not in found_items_in_this_check:
                        found_items_count[item_name] += 1
                        found_items_in_this_check.append((cycle_key, item_config))
                    break
        
        # Обработка найденных предметов
        if found_items_in_this_check:
            logger.info(f"🎯 Найдены предметы в {channel_name}: {len(found_items_in_this_check)} шт")
            
            for cycle_key, item_config in found_items_in_this_check:
                current_time_str = datetime.now().strftime('%H:%M:%S')
                notification = f"✅ Найден {item_config['emoji']} {item_config['display_name']} в {current_time_str}"
                
                # Отправляем уведомление в личный чат
                send_to_bot(notification, disable_notification=False)
                
                # Отправляем стикер в канал
                if send_to_channel(sticker_id=item_config['sticker_id']):
                    logger.info(f"✅ Стикер {item_config['emoji']} отправлен в канал")
                else:
                    logger.error(f"❌ Ошибка отправки стикера {item_config['emoji']}")
            
            # Отмечаем, что в этом цикле уже нашли Kiro
            last_processed_cycles[channel_id] = current_cycle
            bot_status = f"🟢 Найдены предметы в {channel_name}"
            return True
    
    # Если дошли сюда и не нашли предметов, но нашли Kiro
    # Отмечаем цикл как обработанный (Kiro был, но без наших предметов)
    last_processed_cycles[channel_id] = current_cycle
    logger.info(f"📭 Kiro в {channel_name} без нужных предметов")
    bot_status = f"🟢 Проверен {channel_name}"
    return False

# ==================== МОНИТОРЫ ====================
def monitor_seeds():
    """Мониторинг семян (постоянный, каждые 30 секунд)"""
    logger.info("🌱 Запуск мониторинга семян (постоянный)")
    
    while True:
        try:
            if should_check_channel_now(SEEDS_CHANNEL_ID):
                check_channel(SEEDS_CHANNEL_ID)
            
            # Ждем 30 секунд до следующей проверки
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторинге семян: {e}")
            time.sleep(10)

def monitor_eggs():
    """Мониторинг яиц (по расписанию)"""
    logger.info("🥚 Запуск мониторинга яиц (по расписанию)")
    
    while True:
        try:
            if should_check_channel_now(EGGS_CHANNEL_ID):
                check_channel(EGGS_CHANNEL_ID)
            
            # Короткая пауза
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторинге яиц: {e}")
            time.sleep(10)

def monitor_pass_shop():
    """Мониторинг пасс-шопа (по расписанию)"""
    logger.info("🎫 Запуск мониторинга пасс-шопа (по расписанию)")
    
    while True:
        try:
            if should_check_channel_now(PASS_SHOP_CHANNEL_ID):
                check_channel(PASS_SHOP_CHANNEL_ID)
            
            # Короткая пауза
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторинге пасс-шопа: {e}")
            time.sleep(10)

def self_pinger():
    """Самопинг чтобы Render не останавливал сервис (из Ember бота)"""
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
        time.sleep(480)  # 8 минут

def health_monitor():
    """Отправляет статус каждые 6 часов"""
    logger.info("📊 Монитор здоровья запущен (каждые 6 часов)")
    
    time.sleep(60)
    
    report_count = 0
    
    while True:
        try:
            time.sleep(6 * 60 * 60)  # 6 часов
            
            report_count += 1
            uptime = datetime.now() - bot_start_time
            uptime_hours = uptime.total_seconds() / 3600
            
            # Статистика находок
            items_stats = []
            for item_name, count in found_items_count.items():
                if count > 0:
                    item = TARGET_ITEMS[item_name]
                    items_stats.append(f"{item['emoji']} {item['display_name']}: {count}")
            
            stats_text = "\n".join(items_stats) if items_stats else "Еще не найдено"
            
            status_msg = (
                f"📊 <b>АВТО-СТАТУС #{report_count}</b>\n"
                f"⏰ Работает: {uptime_hours:.1f} часов\n"
                f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
                f"🔄 {bot_status}\n"
                f"🏓 Самопинг: {ping_count} раз\n"
                f"💾 Запросов к Discord: {discord_request_count}\n"
                f"📝 В памяти: {len(processed_messages_cache)} сообщений\n\n"
                f"🎯 <b>Найдено предметов:</b>\n"
                f"{stats_text}\n\n"
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
    
    # Текущие циклы
    cycles_status = []
    for channel_id, channel_name in CHANNEL_NAMES.items():
        current_cycle = get_current_cycle(channel_id)
        last_cycle = last_processed_cycles.get(channel_id)
        status = "🟢 Активен" if last_cycle != current_cycle else "⏸️ Обработан"
        cycles_status.append(f"{channel_name}: {status} (цикл: {current_cycle})")
    
    return f"""
    <html>
    <head>
        <title>🌱 Мониторинг Kiro с управлением</title>
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
        </style>
    </head>
    <body>
        <h1>🌱 Мониторинг Kiro с управлением через Telegram</h1>
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> <span class="status-ok">{bot_status}</span></p>
            <p><strong>Время работы:</strong> {uptime_str}</p>
            <p><strong>Запросов к Discord:</strong> {discord_request_count}</p>
            <p><strong>Самопингов:</strong> {ping_count}</p>
            <p><strong>Кэш сообщений:</strong> {len(processed_messages_cache)}</p>
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
            <h2>🎯 Стратегия мониторинга</h2>
            <p><strong>🌱 Семена:</strong> Постоянно, каждые 30 секунд</p>
            <p><strong>🥚 Яйца:</strong> По расписанию (00:30, 02:00, 05:00 в 00 и 30 минут)</p>
            <p><strong>🎫 Пасс-шоп:</strong> По расписанию (:40, 1:10 каждые 5 минут)</p>
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
        'found_items_total': sum(found_items_count.values())
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК МОНИТОРИНГА KIRO С УПРАВЛЕНИЕМ")
    logger.info("=" * 60)
    logger.info("🌱 Семена: постоянно, каждые 30 секунд")
    logger.info("🥚 Яйца: по расписанию (00:30, 02:00, 05:00)")
    logger.info("🎫 Пасс-шоп: по расписанию (:40, 1:10)")
    logger.info("🏓 Самопинг: каждые 8 минут (как Ember)")
    logger.info("📊 Авто-статус: каждые 6 часов")
    logger.info("🎛️ Управление: Telegram команды /start, /status, /enable, /disable")
    logger.info("=" * 60)
    
    # Запуск всех потоков
    threads = [
        threading.Thread(target=monitor_seeds, name='SeedsMonitor', daemon=True),
        threading.Thread(target=monitor_eggs, name='EggsMonitor', daemon=True),
        threading.Thread(target=monitor_pass_shop, name='PassShopMonitor', daemon=True),
        threading.Thread(target=self_pinger, name='SelfPinger', daemon=True),
        threading.Thread(target=health_monitor, name='HealthMonitor', daemon=True),
        threading.Thread(target=telegram_poller, name='TelegramPoller', daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Запущен поток: {thread.name}")
        time.sleep(1)
    
    # Стартовое сообщение в Telegram
    startup_msg = (
        "🚀 <b>МОНИТОРИНГ KIRO ЗАПУЩЕН С УПРАВЛЕНИЕМ</b>\n\n"
        "🌱 <b>Семена:</b> Постоянно, каждые 30 секунд\n"
        "🥚 <b>Яйца:</b> По расписанию (00:30, 02:00, 05:00 в 00 и 30 минут)\n"
        "🎫 <b>Пасс-шоп:</b> По расписанию (:40, 1:10 каждые 5 минут)\n\n"
        "🏓 <b>Самопинг:</b> Активен (каждые 8 минут)\n"
        "📊 <b>Авто-статус:</b> Каждые 6 часов\n"
        "💪 <b>Безопасно для Discord:</b> ~150 запросов в час\n\n"
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
