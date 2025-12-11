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

# ==================== НАСТРОЙКИ ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Получаем ID каналов из переменных окружения
DISCORD_CHANNEL_IDS = []
for var_name in ['SEEDS_CHANNEL_ID', 'EGGS_CHANNEL_ID', 'PASS_SHOP_CHANNEL_ID']:
    channel_id = os.getenv(var_name)
    if channel_id:
        DISCORD_CHANNEL_IDS.append(channel_id.strip())

if not DISCORD_CHANNEL_IDS:
    # Для обратной совместимости
    old_channel_id = os.getenv('DISCORD_CHANNEL_ID')
    if old_channel_id:
        DISCORD_CHANNEL_IDS = [old_channel_id]

logger.info(f"📡 Буду мониторить {len(DISCORD_CHANNEL_IDS)} каналов")

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

# ==================== РАСПИСАНИЕ ОПРОСА ====================
# Разное расписание для разных типов каналов
CHANNEL_SCHEDULES = {}

# Канал семян (первый канал) - частые запросы после обновления
if len(DISCORD_CHANNEL_IDS) >= 1:
    CHANNEL_SCHEDULES[DISCORD_CHANNEL_IDS[0]] = {
        'name': '🌱 Семена',
        'base_interval': 60,  # 1 минута между запросами обычно
        'burst_schedule': [20, 40, 60, 120, 180, 240, 300],  # запросы через N секунд после находки
        'in_burst': False,
        'burst_start': None,
        'burst_index': 0
    }

# Канал яиц (второй канал) - редкие запросы
if len(DISCORD_CHANNEL_IDS) >= 2:
    CHANNEL_SCHEDULES[DISCORD_CHANNEL_IDS[1]] = {
        'name': '🥚 Яйца',
        'base_interval': 300,  # 5 минут между запросами
        'burst_schedule': [30, 60, 120, 300, 600],  # редкие запросы
        'in_burst': False,
        'burst_start': None,
        'burst_index': 0
    }

# Канал пасс-шопа (третий канал) - средние запросы
if len(DISCORD_CHANNEL_IDS) >= 3:
    CHANNEL_SCHEDULES[DISCORD_CHANNEL_IDS[2]] = {
        'name': '🎫 Пасс-шоп',
        'base_interval': 120,  # 2 минуты между запросами
        'burst_schedule': [40, 80, 120, 180],  # средние запросы
        'in_burst': False,
        'burst_start': None,
        'burst_index': 0
    }

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
last_processed_ids = {}
CACHE_FILE = 'last_processed_ids.json'
startup_time = datetime.now()
channel_enabled = True
bot_status = "🟢 Ожидание старта"
last_error = None
processed_messages_cache = set()
telegram_offset = 0
ping_count = 0
last_ping_time = None
found_seeds_count = {name: 0 for name in TARGET_SEEDS.keys()}

# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML"):
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены переменные Telegram")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, data=data, timeout=15)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено в Telegram ({chat_id})")
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
        return False
    
    if not hasattr(send_to_channel, 'last_channel_message_time'):
        send_to_channel.last_channel_message_time = 0
    
    current_time = time.time()
    time_since_last = current_time - send_to_channel.last_channel_message_time
    
    if time_since_last < 2:
        time.sleep(2 - time_since_last)
    
    send_to_channel.last_channel_message_time = time.time()
    
    if sticker_id:
        return send_telegram_sticker(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    
    return False

def send_to_bot(text):
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

def get_discord_messages(channel_id):
    try:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=5"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            retry_after = response.json().get('retry_after', 1)
            logger.warning(f"⚠️ Лимит Discord API, жду {retry_after} сек")
            time.sleep(retry_after)
            return None
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Discord: {e}")
        return None

def process_message(message, channel_id):
    global found_seeds_count, bot_status, last_error
    
    try:
        message_id = message.get('id')
        author = message.get('author', {}).get('username', '')
        
        # Проверяем автора
        if 'kiro' not in author.lower():
            return False
        
        # Проверяем дубли
        if message_id in processed_messages_cache:
            return False
        
        processed_messages_cache.add(message_id)
        
        # Очищаем текст
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
        
        # Форматируем для бота
        cleaned_text = re.sub(r'<:[a-zA-Z0-9_]+:(\d+)>', '', all_text)
        cleaned_text = re.sub(r'\*\*', '', cleaned_text)
        cleaned_text = re.sub(r'<t:\d+:[tR]>', '', cleaned_text)
        
        # Отправляем в бота
        if cleaned_text.strip():
            current_time = datetime.now().strftime('%H:%M:%S')
            channel_name = CHANNEL_SCHEDULES.get(channel_id, {}).get('name', 'Неизвестный')
            
            bot_message = (
                f"📥 Новое сообщение\n"
                f"🤖 Автор: {author}\n"
                f"📡 Канал: {channel_name}\n"
                f"⏰ Время: {current_time}\n\n"
                f"<code>{cleaned_text[:2000]}</code>"
            )
            send_to_bot(bot_message)
        
        # Проверяем на наличие отслеживаемых предметов
        search_text = all_text.lower()
        found_items = []
        
        for seed_name, seed_config in TARGET_SEEDS.items():
            for keyword in seed_config['keywords']:
                if keyword in search_text:
                    found_seeds_count[seed_name] += 1
                    found_items.append(seed_config['display_name'])
                    logger.info(f"🎯 НАЙДЕН {seed_name.upper()} в канале {channel_name}!")
                    
                    # Отправляем стикер в канал
                    send_to_channel(sticker_id=seed_config['sticker_id'])
                    send_to_bot(f"✅ Стикер {seed_config['emoji']} отправлен в канал")
                    
                    # Запускаем burst режим для этого канала
                    if channel_id in CHANNEL_SCHEDULES:
                        CHANNEL_SCHEDULES[channel_id]['in_burst'] = True
                        CHANNEL_SCHEDULES[channel_id]['burst_start'] = time.time()
                        CHANNEL_SCHEDULES[channel_id]['burst_index'] = 0
                        logger.info(f"🚀 Запускаю burst режим для {channel_name}")
        
        bot_status = "🟢 Работает нормально"
        last_error = None
        
        return len(found_items) > 0
        
    except Exception as e:
        error_msg = f"Ошибка обработки: {e}"
        logger.error(f"💥 {error_msg}")
        bot_status = "🔴 Ошибка обработки"
        last_error = error_msg
        return False

def check_channel(channel_id):
    """Проверяет один канал"""
    schedule = CHANNEL_SCHEDULES.get(channel_id, {})
    
    # Определяем интервал проверки
    if schedule.get('in_burst'):
        # В burst режиме
        burst_start = schedule.get('burst_start', 0)
        burst_index = schedule.get('burst_index', 0)
        burst_schedule = schedule.get('burst_schedule', [])
        
        if burst_index < len(burst_schedule):
            # Время следующего burst запроса
            next_burst_time = burst_start + burst_schedule[burst_index]
            if time.time() >= next_burst_time:
                # Выполняем burst запрос
                schedule['burst_index'] = burst_index + 1
                logger.info(f"🔍 Burst запрос #{burst_index+1} для {schedule.get('name')}")
                return True
            else:
                # Еще не время
                return False
        else:
            # Завершаем burst режим
            schedule['in_burst'] = False
            schedule['burst_start'] = None
            schedule['burst_index'] = 0
            logger.info(f"⏹️ Завершен burst режим для {schedule.get('name')}")
            return True
    else:
        # Обычный режим - проверяем по base_interval
        if not hasattr(check_channel, 'last_check_times'):
            check_channel.last_check_times = {}
        
        last_check = check_channel.last_check_times.get(channel_id, 0)
        base_interval = schedule.get('base_interval', 60)
        
        if time.time() - last_check >= base_interval:
            check_channel.last_check_times[channel_id] = time.time()
            return True
        else:
            return False

def monitor_discord():
    logger.info("🔄 Запускаю мониторинг Discord...")
    
    # Ждем немного при старте
    time.sleep(10)
    
    while True:
        try:
            # Проверяем каждый канал по его расписанию
            for channel_id in DISCORD_CHANNEL_IDS:
                if check_channel(channel_id):
                    messages = get_discord_messages(channel_id)
                    if messages:
                        for message in messages:
                            process_message(message, channel_id)
            
            # Чистим кэш если нужно
            if len(processed_messages_cache) > 1000:
                processed_messages_cache.clear()
            
            time.sleep(5)  # Короткая пауза между итерациями
            
        except Exception as e:
            logger.error(f"💥 Ошибка мониторинга: {e}")
            time.sleep(30)

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
        seeds_list = "\n".join([f"{config['emoji']} {config['display_name']}" for config in TARGET_SEEDS.values()])
        channels_list = "\n".join([f"• {sched.get('name', 'Неизвестный')}" for sched in CHANNEL_SCHEDULES.values()])
        
        welcome_text = (
            "🚀 <b>БОТ ЗАПУЩЕН С ОПТИМИЗАЦИЕЙ ЗАПРОСОВ!</b>\n\n"
            f"📡 <b>Мониторю каналы:</b>\n{channels_list}\n\n"
            f"🎯 <b>Отслеживаю:</b>\n{seeds_list}\n\n"
            "⚡ <b>Новая логика:</b>\n"
            "• Разные интервалы для разных каналов\n"
            "• Burst запросы после находки семян\n"
            "• Экономия запросов к Discord\n\n"
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
    
    channels_info = []
    for channel_id, schedule in CHANNEL_SCHEDULES.items():
        status = "🟢 Burst" if schedule.get('in_burst') else "⚪ Обычный"
        channels_info.append(f"{schedule.get('name')}: {status}")
    
    status_text = (
        f"📊 <b>Статус бота</b>\n\n"
        f"{bot_status}\n"
        f"⏰ Работает: {hours:.1f} часов\n"
        f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"📡 Каналов: {len(CHANNEL_SCHEDULES)}\n"
        f"🏓 Самопинг: {ping_count} раз\n"
        f"💾 Кэш: {len(processed_messages_cache)} сообщений\n\n"
        f"📡 <b>Каналы:</b>\n" + "\n".join(channels_info) + "\n\n"
        f"🎯 <b>Найдено:</b>\n{seeds_stats}"
    )
    
    if last_error:
        status_text += f"\n\n⚠️ <b>Ошибка:</b>\n<code>{last_error}</code>"
    
    send_telegram_message(chat_id, status_text)

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    seeds_list = ", ".join([f"{config['emoji']} {config['display_name']}" for config in TARGET_SEEDS.values()])
    
    channels_list = []
    for schedule in CHANNEL_SCHEDULES.values():
        status = "🟢 Burst" if schedule.get('in_burst') else "⚪ Обычный"
        channels_list.append(f"• {schedule.get('name')} - {status}")
    
    return f"""
    <html>
        <head><title>🌱 Seed Monitor</title></head>
        <body>
            <h1>🌱 Мониторинг семян</h1>
            <p><strong>Статус:</strong> {bot_status}</p>
            <p><strong>Время работы:</strong> {hours:.1f} часов</p>
            <p><strong>Каналов:</strong> {len(CHANNEL_SCHEDULES)}</p>
            <p><strong>Отслеживаю:</strong> {seeds_list}</p>
            <h3>📡 Каналы:</h3>
            <pre>{chr(10).join(channels_list)}</pre>
            <p><a href="/enable_channel">✅ Включить канал</a> | 
               <a href="/disable_channel">⏸️ Выключить канал</a></p>
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
    # Проверяем настройки
    if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL_ID or not TELEGRAM_BOT_CHAT_ID:
        logger.error("❌ Не настроены переменные Telegram!")
    
    if not DISCORD_TOKEN:
        logger.error("❌ Не настроен токен Discord!")
    
    if not DISCORD_CHANNEL_IDS:
        logger.error("❌ Не указаны каналы Discord!")
    
    logger.info(f"🚀 Запуск бота")
    logger.info(f"📡 Каналы: {len(DISCORD_CHANNEL_IDS)}")
    logger.info(f"🎯 Предметов: {len(TARGET_SEEDS)}")
    
    # Запускаем потоки
    threads = [
        threading.Thread(target=monitor_discord, daemon=True),
        threading.Thread(target=telegram_poller, daemon=True),
        threading.Thread(target=simple_self_pinger, daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Запущен {thread.name}")
    
    # Стартовое сообщение
    try:
        startup_msg = (
            "🚀 <b>БОТ ЗАПУЩЕН С ОПТИМИЗАЦИЕЙ!</b>\n\n"
            f"📡 <b>Каналов:</b> {len(DISCORD_CHANNEL_IDS)}\n"
            f"🎯 <b>Предметов:</b> {len(TARGET_SEEDS)}\n"
            f"⚡ <b>Логика:</b> Оптимизированные запросы\n\n"
            "✅ <b>Готов к работе!</b>\n"
            "Отправьте /status для проверки."
        )
        send_to_bot(startup_msg)
    except Exception as e:
        logger.error(f"❌ Не удалось отправить стартовое сообщение: {e}")
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
