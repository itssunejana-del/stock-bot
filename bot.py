from flask import Flask, request
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
import re
import json

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== КОНФИГУРАЦИЯ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SEEDS_CHANNEL_ID = os.getenv('SEEDS_CHANNEL_ID')
EGGS_CHANNEL_ID = os.getenv('EGGS_CHANNEL_ID')
PASS_SHOP_CHANNEL_ID = os.getenv('PASS_SHOP_CHANNEL_ID')

# Проверка критически важных переменных
CRITICAL_VARS = {
    'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
    'TELEGRAM_CHANNEL_ID': TELEGRAM_CHANNEL_ID,
    'TELEGRAM_BOT_CHAT_ID': TELEGRAM_BOT_CHAT_ID,
    'DISCORD_TOKEN': DISCORD_TOKEN,
    'SEEDS_CHANNEL_ID': SEEDS_CHANNEL_ID,
    'EGGS_CHANNEL_ID': EGGS_CHANNEL_ID,
    'PASS_SHOP_CHANNEL_ID': PASS_SHOP_CHANNEL_ID
}
missing_vars = [name for name, value in CRITICAL_VARS.items() if not value]
if missing_vars:
    logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Отсутствуют переменные окружения: {', '.join(missing_vars)}")
    # Не выходим, но логируем ошибку. Бот попытается работать с тем, что есть.

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

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ И СОСТОЯНИЕ ====================
# Для хранения последних обработанных ID (ключ: channel_id, значение: message_id)
last_processed_ids = {}
# Файл для сохранения состояния между перезапусками
STATE_FILE = 'bot_state.json'
# Кэш для предотвращения повторной обработки одних и тех же сообщений в течение сессии
processed_messages_cache = set()
# Кэш для предотвращения отправки одинаковых стикеров в течение одного цикла обновления
sent_stickers_cache = {}
# Общая статистика
bot_start_time = datetime.now()
bot_status = "🟢 Инициализация"
channel_enabled = True  # Флаг включения/выключения отправки в Telegram-канал

# ==================== РАСПИСАНИЕ ЗАПРОСОВ ====================
# Ключ: ID канала Discord, Значение: список кортежей (минута, секунда) относительно начала цикла
REQUEST_SCHEDULE = {}
CHANNEL_NAMES = {}
CHANNEL_CYCLE_MINUTES = {}  # Длина цикла обновления для канала (5 или 30 минут)

if SEEDS_CHANNEL_ID:
    REQUEST_SCHEDULE[SEEDS_CHANNEL_ID] = [(0, 20), (0, 40), (1, 0), (2, 0), (3, 0)]
    CHANNEL_NAMES[SEEDS_CHANNEL_ID] = '🌱 Семена'
    CHANNEL_CYCLE_MINUTES[SEEDS_CHANNEL_ID] = 5
if EGGS_CHANNEL_ID:
    REQUEST_SCHEDULE[EGGS_CHANNEL_ID] = [(0, 30), (1, 0), (2, 0), (5, 0), (10, 0), (20, 0)]
    CHANNEL_NAMES[EGGS_CHANNEL_ID] = '🥚 Яйца'
    CHANNEL_CYCLE_MINUTES[EGGS_CHANNEL_ID] = 30
if PASS_SHOP_CHANNEL_ID:
    REQUEST_SCHEDULE[PASS_SHOP_CHANNEL_ID] = [(0, 40), (1, 10), (1, 40)]
    CHANNEL_NAMES[PASS_SHOP_CHANNEL_ID] = '🎫 Пасс-шоп'
    CHANNEL_CYCLE_MINUTES[PASS_SHOP_CHANNEL_ID] = 5

logger.info(f"📡 Загружено расписание для {len(REQUEST_SCHEDULE)} каналов.")

# ==================== СИСТЕМА СОХРАНЕНИЯ И ЗАГРУЗКИ СОСТОЯНИЯ ====================
def save_bot_state():
    """Сохраняет last_processed_ids в файл."""
    try:
        state_data = {
            'last_processed_ids': last_processed_ids,
            'saved_at': datetime.now().isoformat()
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state_data, f, indent=2)
        logger.debug(f"💾 Состояние сохранено для {len(last_processed_ids)} каналов.")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения состояния: {e}")

def load_bot_state():
    """Загружает last_processed_ids из файла."""
    global last_processed_ids
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state_data = json.load(f)
                loaded_ids = state_data.get('last_processed_ids', {})
                # Обновляем только для каналов, которые у нас есть в конфигурации
                for ch_id in REQUEST_SCHEDULE:
                    if ch_id in loaded_ids:
                        last_processed_ids[ch_id] = loaded_ids[ch_id]
                logger.info(f"📂 Состояние загружено из файла ({len(loaded_ids)} каналов).")
        else:
            logger.info("📂 Файл состояния не найден. Начинаем с чистого листа.")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки состояния: {e}")
# ==================== СИСТЕМА СОХРАНЕНИЯ ОТПРАВЛЕННЫХ СТИКЕРОВ ====================
STICKERS_STATE_FILE = 'sent_stickers_state.json'
sent_stickers_state = {}  # Формат: {"channel_id_itemname_hourcycle": true}

def load_stickers_state():
    """Загружает историю отправленных стикеров из файла."""
    global sent_stickers_state
    try:
        if os.path.exists(STICKERS_STATE_FILE):
            with open(STICKERS_STATE_FILE, 'r') as f:
                sent_stickers_state = json.load(f)
            logger.debug(f"🎯 Загружена история стикеров: {len(sent_stickers_state)} записей")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки истории стикеров: {e}")
        sent_stickers_state = {}

def save_stickers_state():
    """Сохраняет историю отправленных стикеров в файл."""
    try:
        with open(STICKERS_STATE_FILE, 'w') as f:
            json.dump(sent_stickers_state, f, indent=2)
        logger.debug("💾 История стикеров сохранена")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения истории стикеров: {e}")

def was_sticker_sent_in_cycle(channel_id, item_name):
    """Проверяет, был ли стикер для этого предмета отправлен в текущем цикле."""
    cycle_key = get_current_cycle_key(channel_id)
    state_key = f"{cycle_key}_{item_name}"
    return sent_stickers_state.get(state_key, False)

def mark_sticker_sent_in_cycle(channel_id, item_name):
    """Отмечает, что стикер для этого предмета отправлен в текущем цикле."""
    cycle_key = get_current_cycle_key(channel_id)
    state_key = f"{cycle_key}_{item_name}"
    sent_stickers_state[state_key] = True
    save_stickers_state()
    logger.debug(f"📝 Отмечен отправленный стикер: {item_name} в цикле {cycle_key}")

# ==================== ФУНКЦИИ ДЛЯ TELEGRAM ====================
def send_telegram_message(chat_id, text, parse_mode="HTML", disable_notification=False):
    """Универсальная функция отправки сообщения в Telegram."""
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
        response = requests.post(url, json=data, timeout=15)
        if response.status_code == 200:
            logger.debug(f"📨 Сообщение отправлено в Telegram (chat_id: {chat_id})")
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram. Пауза {retry_after} сек.")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Ошибка Telegram API {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка сети при отправке в Telegram: {e}")
        return False

def send_telegram_sticker(chat_id, sticker_id, disable_notification=True):
    """Функция отправки стикера в Telegram."""
    if not TELEGRAM_TOKEN or not chat_id or not sticker_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {
            "chat_id": chat_id,
            "sticker": sticker_id,
            "disable_notification": disable_notification
        }
        response = requests.post(url, json=data, timeout=15)
        if response.status_code == 200:
            logger.info(f"🎉 Стикер отправлен в канал.")
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram (стикер). Пауза {retry_after} сек.")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Ошибка отправки стикера {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка сети при отправке стикера: {e}")
        return False

def send_to_channel(sticker_id=None, text=None):
    """Отправляет стикер или сообщение в основной Telegram-канал с защитой от флуда."""
    if not channel_enabled or not TELEGRAM_CHANNEL_ID:
        return False
    # Защита от слишком частых сообщений (минимум 2 секунды между отправками)
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
    """Отправляет сообщение в личные сообщения с ботом."""
    if not TELEGRAM_BOT_CHAT_ID:
        return False
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text, disable_notification=disable_notification)

# ==================== ФУНКЦИИ ДЛЯ DISCORD API ====================
def fetch_discord_messages(channel_id, limit=3):
    """Безопасно получает сообщения из канала Discord с обработкой лимитов."""
    if not DISCORD_TOKEN or not channel_id:
        return None
    try:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        # Увеличиваем таймаут для стабильности
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 200:
            messages = response.json()
            # Фильтруем сообщения, оставляя только от Kiro
            filtered_messages = [msg for msg in messages if is_message_from_kiro(msg)]
            if filtered_messages:
                logger.debug(f"📨 Получено {len(filtered_messages)} сообщений от Kiro из канала {CHANNEL_NAMES.get(channel_id, channel_id)}.")
            return filtered_messages
        elif response.status_code == 429:
            error_data = response.json()
            retry_after = error_data.get('retry_after', 2.0)
            logger.warning(f"⏳ Discord API лимит. Жду {retry_after} сек. (Канал: {CHANNEL_NAMES.get(channel_id, channel_id)})")
            time.sleep(retry_after)
            return None
        else:
            logger.error(f"❌ Ошибка Discord API ({response.status_code}) для канала {CHANNEL_NAMES.get(channel_id, channel_id)}: {response.text[:200]}")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"⏰ Таймаут запроса к Discord API (канал: {CHANNEL_NAMES.get(channel_id, channel_id)})")
        return None
    except Exception as e:
        logger.error(f"❌ Неизвестная ошибка при запросе к Discord: {e}")
        return None

def is_message_from_kiro(message_data):
    """Проверяет, является ли автор сообщения ботом Kiro."""
    author = message_data.get('author', {})
    username = author.get('username', '').lower()
    is_bot = author.get('bot', False)
    # Ищем "kiro" в имени пользователя или считаем всех ботов Kiro, если других ботов нет
    return ('kiro' in username) or (is_bot and 'kiro' in username)

def clean_discord_text(text):
    """Очищает текст от Discord-форматирования для читаемого отображения в Telegram."""
    if not text:
        return ""
    # Удаляем форматы типа <:name:id> и <t:timestamp:R>
    text = re.sub(r'<[:@#!]?[a-zA-Z0-9_]+:(\d+)>', '', text)
    text = re.sub(r'<t:\d+:[tTdDfFR]>', '', text)
    text = re.sub(r'[*_~`|]', '', text)  # Удаляем markdown
    # Убираем множественные переносы строк
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)

def extract_text_from_message(message_data):
    """Извлекает и объединяет весь текст из сообщения Discord (контент + эмбеды)."""
    full_text = message_data.get('content', '')
    for embed in message_data.get('embeds', []):
        if embed.get('title'):
            full_text += f"\n{embed.get('title')}"
        if embed.get('description'):
            full_text += f"\n{embed.get('description')}"
        for field in embed.get('fields', []):
            full_text += f"\n{field.get('name', '')}: {field.get('value', '')}"
    return full_text.lower()

# ==================== ОСНОВНАЯ ЛОГИКА ОБРАБОТКИ ====================
def process_discord_message(message_data, channel_id):
    """Обрабатывает одно сообщение от Kiro: проверяет предметы, шлет уведомления."""
    global last_processed_ids, sent_stickers_cache, bot_status
    try:
        message_id = message_data['id']
        channel_name = CHANNEL_NAMES.get(channel_id, channel_id)

        # 1. ПРОВЕРКА ДУБЛЯ: Пропускаем, если уже обрабатывали в этой сессии
        if message_id in processed_messages_cache:
            logger.debug(f"⏭️ Пропущен дубль сообщения {message_id} в канале {channel_name}.")
            return False

        # 2. ПРОВЕРКА НОВИЗНЫ: Пропускаем, если сообщение старше последнего обработанного
        last_id_for_channel = last_processed_ids.get(channel_id)
        if last_id_for_channel and int(message_id) <= int(last_id_for_channel):
            logger.debug(f"⏭️ Пропущено старое сообщение {message_id} (последнее: {last_id_for_channel}) в {channel_name}.")
            return False

        logger.info(f"🔍 Обрабатываю новое сообщение {message_id} из {channel_name}.")

        # 3. ИЗВЛЕЧЕНИЕ И АНАЛИЗ ТЕКСТА
        full_text = extract_text_from_message(message_data)
        found_items = []
        found_seed_names = []

        for seed_name, seed_config in TARGET_SEEDS.items():
            for keyword in seed_config['keywords']:
                if keyword in full_text:
                    found_items.append(seed_config)
                    found_seed_names.append(seed_name)
                    logger.info(f"🎯 Найден {seed_config['emoji']} {seed_config['display_name']} в {channel_name}!")
                    break  # Не ищем другие ключевые слова для этого семени

       # 4. ОБРАБОТКА НАЙДЕННЫХ ПРЕДМЕТОВ
sticker_sent_in_this_message = False
if found_items:
    # Определяем уникальный ключ для кэша стикеров в этом цикле обновления
    current_cycle_key = get_current_cycle_key(channel_id)

    for seed_config in found_items:
        item_name = seed_config['display_name']
        cache_key = f"{current_cycle_key}_{item_name}"
        
        # ПРОВЕРКА 1: Не отправлен ли в текущей сессии (память)
        # ПРОВЕРКА 2: Не отправлен ли до перезапуска (файл)
        if (cache_key not in sent_stickers_cache and 
            not was_sticker_sent_in_cycle(channel_id, item_name)):
            
            if send_to_channel(sticker_id=seed_config['sticker_id']):
                # Сохраняем в ДВА места:
                sent_stickers_cache[cache_key] = True  # Память (быстрый доступ)
                mark_sticker_sent_in_cycle(channel_id, item_name)  # Файл (переживает перезапуск)
                
                sticker_sent_in_this_message = True
                # Уведомляем в личку о отправке стикера
                send_to_bot(f"✅ Стикер {seed_config['emoji']} отправлен в канал из {channel_name}.", disable_notification=True)
                logger.info(f"🎯 Стикер {seed_config['emoji']} {item_name} отправлен и запомнен.")
            else:
                logger.error(f"❌ Не удалось отправить стикер {seed_config['emoji']}.")
        else:
            logger.debug(f"⏭️ Стикер {seed_config['emoji']} {item_name} уже был отправлен в этом цикле.")

        # 5. ОТПРАВКА ИНФОРМАЦИИ В ЛИЧКУ БОТА
        # Отправляем всегда, если нашли отслеживаемые предметы, или если это первое сообщение после простоя
        if found_items or not last_id_for_channel:
            cleaned_content = clean_discord_text(message_data.get('content', ''))
            # Форматируем красивое сообщение для Telegram
            items_text = ', '.join([f"{item['emoji']} {item['display_name']}" for item in found_items]) if found_items else "Нет отслеживаемых предметов"
            current_time = datetime.now().strftime('%H:%M:%S')
            message_for_bot = (
                f"📥 **Сообщение от Kiro**\n"
                f"**Канал:** {channel_name}\n"
                f"**Время:** {current_time}\n"
                f"**Найдено:** {items_text}\n"
                f"```\n{cleaned_content[:500]}\n```"
            )
            send_to_bot(message_for_bot, disable_notification=not found_items)

        # 6. ОБНОВЛЕНИЕ СОСТОЯНИЯ
        processed_messages_cache.add(message_id)
        last_processed_ids[channel_id] = message_id
        save_bot_state()  # Сохраняем прогресс

        bot_status = f"🟢 Обработан {channel_name}"
        return bool(found_items)  # Возвращаем True, если нашли хоть один предмет

    except Exception as e:
        logger.error(f"💥 Критическая ошибка обработки сообщения в {channel_name}: {e}")
        return False

def get_current_cycle_key(channel_id):
    """Генерирует уникальный ключ для каждого цикла обновления в сутках."""
    now = datetime.now()
    cycle_length = CHANNEL_CYCLE_MINUTES.get(channel_id, 5)
    
    # Вычисляем номер цикла с ПОЛНОЧИ
    total_minutes_since_midnight = now.hour * 60 + now.minute
    cycle_number = total_minutes_since_midnight // cycle_length
    
    # Для отладки - можно залогировать
    if now.minute % cycle_length == 0 and now.second < 5:
        logger.debug(f"🔄 Цикл #{cycle_number} для {CHANNEL_NAMES.get(channel_id)} ({cycle_length} мин)")
    
    # Уникальный ключ: дата_номер_цикла_канал
    date_str = now.strftime('%Y%m%d')
    return f"{date_str}_{cycle_number:04d}_{channel_id}"  # 4 цифры для номера цикла

def should_check_channel_now(channel_id):
    """Определяет, нужно ли прямо сейчас делать запрос к каналу согласно расписанию."""
    if channel_id not in REQUEST_SCHEDULE:
        return False

    now = datetime.now()
    current_minute = now.minute
    current_second = now.second

    # Определяем, в какой минуте цикла обновления мы находимся
    cycle_length = CHANNEL_CYCLE_MINUTES.get(channel_id, 5)
    minute_in_cycle = current_minute % cycle_length

    # Проверяем, совпадает ли текущее время с одним из запланированных
    for scheduled_minute, scheduled_second in REQUEST_SCHEDULE[channel_id]:
        if minute_in_cycle == scheduled_minute and current_second == scheduled_second:
            return True
    return False

# ==================== ФОНОВЫЕ ПОТОКИ И МОНИТОРИНГ ====================
def schedule_monitor():
    """Главный цикл мониторинга. Проверяет расписание и выполняет запросы к Discord."""
    logger.info("👁️‍🗨️ Монитор расписания запущен.")
    load_bot_state()  # Загружаем сохраненное состояние при старте
    load_stickers_state()  # Загружаем историю отправленных стикеров
    send_to_bot("🚀 **Мониторинг Discord запущен по новому расписанию.**\nБот запомнил последние обработанные сообщения и не будет присылать старые.")

    # Инициализация: делаем первый запрос, чтобы узнать последние сообщения, но не шлем уведомления
    for channel_id in REQUEST_SCHEDULE:
        channel_name = CHANNEL_NAMES.get(channel_id, channel_id)
        logger.info(f"🔍 Первичная проверка канала {channel_name}...")
        messages = fetch_discord_messages(channel_id, limit=1)
        if messages:
            last_msg_id = messages[0]['id']
            if channel_id not in last_processed_ids:
                last_processed_ids[channel_id] = last_msg_id
                logger.info(f"   Установлен last_processed_id для {channel_name}: {last_msg_id}")
        time.sleep(1)  # Пауза между первичными запросами
    save_bot_state()

    # Основной цикл с фиксированным интервалом (проверяем расписание каждую секунду)
    while True:
        try:
            now_ts = time.time()
            # Проверяем каждый канал
            for channel_id in REQUEST_SCHEDULE:
                if should_check_channel_now(channel_id):
                    channel_name = CHANNEL_NAMES.get(channel_id, channel_id)
                    logger.info(f"🕐 [РАСПИСАНИЕ] Запрос к {channel_name}")

                    messages = fetch_discord_messages(channel_id)
                    if messages:
                        # Обрабатываем сообщения в порядке от новых к старым
                        for msg in messages:
                            process_discord_message(msg, channel_id)
                    # Делаем небольшую паузу после запроса, даже если сообщений нет
                    time.sleep(0.5)

            # Очистка кэшей раз в 10 минут для предотвращения утечек памяти
            if int(time.time()) % 600 == 0:  # Каждые 600 секунд
                old_cache_size = len(processed_messages_cache)
                # Оставляем только последние 200 записей
                if old_cache_size > 200:
                    processed_messages_cache.clear()
                    logger.debug(f"🧹 Очищен кэш обработанных сообщений. Было: {old_cache_size}")

            # Короткая пауза в конце итерации цикла
            time.sleep(0.5)

        except Exception as e:
            logger.error(f"💥 Непредвиденная ошибка в главном цикле мониторинга: {e}")
            time.sleep(10)

def telegram_command_poller():
    """Фоновая задача для обработки команд из Telegram."""
    logger.info("🤖 Поллер Telegram-команд запущен.")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {'offset': offset, 'timeout': 25, 'limit': 1}
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('ok') and data.get('result'):
                    for update in data['result']:
                        offset = update['update_id'] + 1
                        if 'message' in update and 'text' in update['message']:
                            handle_telegram_command(update['message'])
            else:
                logger.warning(f"⚠️ Неудачный запрос к Telegram API: {resp.status_code}")
                time.sleep(5)
        except requests.exceptions.Timeout:
            continue  # Таймаут - это нормально для long polling
        except Exception as e:
            logger.error(f"❌ Ошибка в поллере Telegram: {e}")
            time.sleep(10)

def handle_telegram_command(message):
    """Обрабатывает команды, присланные боту в личку."""
    chat_id = message['chat']['id']
    text = message['text'].strip()

    if text == '/start' or text == '/help':
        help_text = (
            "🤖 **Бот мониторинга Discord (Kiro)**\n\n"
            "**Команды:**\n"
            "• /status - Показать текущий статус бота\n"
            "• /enable - Включить отправку стикеров в канал\n"
            "• /disable - Выключить отправку стикеров в канал\n"
            "• /help - Показать это сообщение\n\n"
            "**Расписание запросов:**\n"
            "• 🌱 Семена: 20с, 40с, 1м, 2м, 3м после обновления\n"
            "• 🥚 Яйца: 30с, 1м, 2м, 5м, 10м, 20м после обновления\n"
            "• 🎫 Пасс-шоп: 40с, 1м10с, 1м40с после обновления\n\n"
            "_Бот запоминает последние сообщения и не присылает старые._"
        )
        send_telegram_message(chat_id, help_text)
    elif text == '/status':
        send_status(chat_id)
    elif text == '/enable':
        global channel_enabled
        channel_enabled = True
        send_telegram_message(chat_id, "✅ **Отправка стикеров в канал ВКЛЮЧЕНА.**")
    elif text == '/disable':
        channel_enabled = False
        send_telegram_message(chat_id, "⏸️ **Отправка стикеров в канал ВЫКЛЮЧЕНА.**")
    else:
        send_telegram_message(chat_id, "❌ Неизвестная команда. Используйте /help для списка команд.")

def send_status(chat_id):
    """Формирует и отправляет подробный статус бота."""
    uptime = datetime.now() - bot_start_time
    uptime_str = str(uptime).split('.')[0]
    channels_status = []
    for ch_id, ch_name in CHANNEL_NAMES.items():
        last_id = last_processed_ids.get(ch_id, 'Не обработано')
        channels_status.append(f"{ch_name}: `{last_id}`")

    status_msg = (
        f"📊 **Статус бота**\n\n"
        f"**Состояние:** {bot_status}\n"
        f"**Время работы:** {uptime_str}\n"
        f"**Канал (стикеры):** {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"**Мониторю каналов:** {len(REQUEST_SCHEDULE)}\n"
        f"**Кэш сессии:** {len(processed_messages_cache)} сообщ.\n\n"
        f"**Последние обработанные ID:**\n" + '\n'.join(channels_status)
    )
    send_telegram_message(chat_id, status_msg)

# ==================== ВЕБ-ИНТЕРФЕЙС (Flask маршруты) ====================
@app.route('/')
def home():
    """Главная страница веб-интерфейса."""
    uptime = datetime.now() - bot_start_time
    uptime_str = str(uptime).split('.')[0]
    channels_list = "\n".join([f"<li>{name} (Цикл: {CHANNEL_CYCLE_MINUTES.get(cid, 5)} мин.)</li>" for cid, name in CHANNEL_NAMES.items()])
    return f"""
    <html><head><title>Discord Monitor Bot</title><meta charset="utf-8"></head>
    <body style="font-family: sans-serif; padding: 2rem;">
        <h1>🤖 Discord Monitor Bot (Kiro)</h1>
        <p><strong>Статус:</strong> {bot_status}</p>
        <p><strong>Время работы:</strong> {uptime_str}</p>
        <p><strong>Telegram-канал:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</p>
        <hr>
        <h3>📡 Отслеживаемые каналы:</h3>
        <ul>{channels_list}</ul>
        <h3>🎯 Отслеживаемые предметы:</h3>
        <p>{', '.join([s['emoji'] + ' ' + s['display_name'] for s in TARGET_SEEDS.values()])}</p>
        <p><em>Сервис работает в фоновом режиме. Управление через Telegram-бота.</em></p>
    </body></html>
    """

@app.route('/health')
def health_check():
    """Эндпоинт для проверки здоровья сервиса."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': (datetime.now() - bot_start_time).total_seconds(),
        'monitored_channels': len(REQUEST_SCHEDULE)
    }), 200

# ==================== ЗАПУСК ПРИЛОЖЕНИЯ ====================
if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК ОБНОВЛЕННОГО БОТА ДЛЯ KIRO")
    logger.info("=" * 50)
    logger.info(f"🎯 Отслеживаю предметов: {len(TARGET_SEEDS)}")
    logger.info(f"📡 Мониторю каналов: {len(REQUEST_SCHEDULE)}")
    for ch_id, ch_name in CHANNEL_NAMES.items():
        schedule_str = ', '.join([f"{m}м{s}с" for m, s in REQUEST_SCHEDULE[ch_id]])
        logger.info(f"   • {ch_name}: {schedule_str}")

    # Запускаем фоновые потоки
    threads = []
    # Поток мониторинга по расписанию
    monitor_thread = threading.Thread(target=schedule_monitor, name='ScheduleMonitor', daemon=True)
    threads.append(monitor_thread)
    # Поток обработки команд Telegram
    telegram_thread = threading.Thread(target=telegram_command_poller, name='TelegramPoller', daemon=True)
    threads.append(telegram_thread)

    for t in threads:
        t.start()
        logger.info(f"✅ Запущен поток: {t.name}")

    # Запускаем Flask-сервер
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер запускается на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
