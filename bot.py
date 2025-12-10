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

# 🆕 МНОЖЕСТВЕННЫЕ КАНАЛЫ
DISCORD_CHANNEL_IDS_STR = os.getenv('DISCORD_CHANNEL_IDS', '917417,381036,446956')
DISCORD_CHANNEL_IDS = [ch.strip() for ch in DISCORD_CHANNEL_IDS_STR.split(',') if ch.strip()]
logger.info(f"📡 Настроено {len(DISCORD_CHANNEL_IDS)} каналов для мониторинга")

RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')

# 🆕 ОБНОВЛЕННЫЕ настройки отслеживаемых семян
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
    'zebrazinkle': {
        'keywords': ['zebrazinkle', 'zebra zinkle', ':zebrazinkle'],
        'sticker_id': "CAACAgIAAxkBAAEPwjJpFDhW_6Vu29vF7DrTHFBcSf_WIAAC1XkAAkCXoUgr50G4SlzwrzYE",
        'emoji': '🦓',
        'display_name': 'Zebrazinkle'
    }
}

# 🆕 ИМЯ БОТА
BOT_NAME_TO_TRACK = os.getenv('BOT_NAME_TO_TRACK', 'Kiro')

# Глобальные переменные
last_processed_ids = {}
CACHE_FILE = '/tmp/last_processed_ids.json'
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
    """Сохраняет последние обработанные ID"""
    try:
        save_data = {
            'last_processed_ids': last_processed_ids,
            'saved_at': datetime.now().isoformat()
        }
        with open(CACHE_FILE, 'w') as f:
            json.dump(save_data, f, indent=2)
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения кэша: {e}")

def load_last_processed_ids():
    """Загружает последние обработанные ID"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                return data.get('last_processed_ids', {})
        return {}
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки кэша: {e}")
        return {}

def self_pinger():
    """Самопинг чтобы Render не останавливал сервис"""
    global ping_count, last_ping_time
    time.sleep(30)
    
    while True:
        try:
            ping_count += 1
            last_ping_time = datetime.now()
            response = requests.get(f"{RENDER_SERVICE_URL}/", timeout=10)
            if response.status_code == 200:
                logger.info(f"🏓 Самопинг #{ping_count} успешен")
            else:
                logger.warning(f"⚠️ Самопинг: статус {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
        time.sleep(480)

def send_telegram_message(chat_id, text, parse_mode="HTML"):
    """Отправляет сообщение в Telegram"""
    if not TELEGRAM_TOKEN or not chat_id:
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, data=data, timeout=15)
        return response.status_code == 200
    except Exception:
        return False

def send_telegram_sticker(chat_id, sticker_id):
    """Отправляет стикер в Telegram"""
    if not TELEGRAM_TOKEN or not chat_id:
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {"chat_id": chat_id, "sticker": sticker_id}
        response = requests.post(url, data=data, timeout=15)
        return response.status_code == 200
    except Exception:
        return False

def send_to_channel(text=None, sticker_id=None):
    """Отправляет сообщение или стикер в канал"""
    if not channel_enabled:
        return False
    
    if sticker_id:
        return send_telegram_sticker(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    return False

def send_to_bot(text):
    """Отправляет сообщение в бота"""
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

def test_discord_connection():
    """Тестирует подключение к Discord"""
    if not DISCORD_TOKEN:
        logger.error("❌ Discord токен не установлен!")
        return False
    
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    
    # Сначала проверяем токен
    try:
        response = requests.get(
            "https://discord.com/api/v10/users/@me",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            user_info = response.json()
            logger.info(f"✅ Токен Discord валиден! Бот: {user_info.get('username')}")
            return True
        else:
            logger.error(f"❌ Неверный токен Discord: {response.status_code}")
            send_to_bot(f"❌ <b>ОШИБКА DISCORD:</b> Токен неверный (код: {response.status_code})")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Discord: {e}")
        send_to_bot(f"❌ <b>ОШИБКА СЕТИ:</b> Не могу подключиться к Discord: {e}")
        return False

def get_discord_messages_simple(channel_id):
    """Упрощенный запрос сообщений из Discord"""
    if not DISCORD_TOKEN:
        return []
    
    try:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=3"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        # Очень большие таймауты для тестирования
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            messages = response.json()
            for msg in messages:
                msg['source_channel_id'] = channel_id
            logger.info(f"✅ Получено {len(messages)} сообщений из канала {channel_id}")
            return messages
        elif response.status_code == 429:
            logger.warning(f"⚠️ Rate limit для канала {channel_id}")
            time.sleep(5)
            return []
        else:
            logger.error(f"❌ Ошибка {response.status_code} для канала {channel_id}")
            return []
            
    except requests.exceptions.Timeout:
        logger.error(f"⏱️ Таймаут для канала {channel_id}")
        return []
    except Exception as e:
        logger.error(f"💥 Ошибка для канала {channel_id}: {e}")
        return []

def clean_discord_text(text):
    """Очищает текст Discord"""
    text = re.sub(r'<:[a-zA-Z0-9_]+:(\d+)>', '', text)
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'<t:\d+:[tR]>', '', text)
    return text.strip()

def format_message(message):
    """Форматирует сообщение"""
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
    
    return clean_discord_text(full_text)

def process_messages(messages):
    """Обрабатывает сообщения"""
    global last_processed_ids, found_seeds_count
    
    found_any_seed = False
    
    for message in messages:
        channel_id = message.get('source_channel_id')
        message_id = message.get('id')
        
        if not channel_id or not message_id:
            continue
        
        # Проверяем, не обрабатывали ли уже
        last_id = last_processed_ids.get(channel_id)
        if last_id and int(message_id) <= int(last_id):
            continue
        
        # Проверяем автора
        author = message.get('author', {}).get('username', '')
        is_bot = message.get('author', {}).get('bot', False)
        
        if not (is_bot or BOT_NAME_TO_TRACK.lower() in author.lower()):
            continue
        
        # Обрабатываем сообщение
        formatted = format_message(message)
        if not formatted:
            continue
        
        # Ищем семена
        full_text = formatted.lower()
        found_seeds = []
        
        for seed_name, seed_config in TARGET_SEEDS.items():
            for keyword in seed_config['keywords']:
                if keyword in full_text:
                    found_seeds_count[seed_name] += 1
                    found_seeds.append(seed_config['display_name'])
                    
                    # Отправляем стикер
                    send_to_channel(sticker_id=seed_config['sticker_id'])
                    found_any_seed = True
                    break
        
        # Отправляем в бота
        current_time = datetime.now().strftime('%H:%M:%S')
        if found_seeds:
            seeds_str = ", ".join(found_seeds)
            bot_msg = f"⏰Найдены семена: {seeds_str}\nСток {current_time}\n\n<code>{formatted}</code>"
        else:
            bot_msg = f"Сток {current_time}\n\n<code>{formatted}</code>"
        
        send_to_bot(bot_msg)
        
        # Обновляем последний ID
        last_processed_ids[channel_id] = message_id
    
    if last_processed_ids:
        save_last_processed_ids()
    
    return found_any_seed

def monitor_discord_simple():
    """Упрощенный мониторинг Discord"""
    logger.info("🔄 Запускаю упрощенный мониторинг Discord...")
    
    # Сначала тестируем подключение
    if not test_discord_connection():
        logger.error("❌ Не могу подключиться к Discord. Жду 5 минут...")
        time.sleep(300)
        return
    
    # Загружаем кэш
    global last_processed_ids
    last_processed_ids = load_last_processed_ids()
    
    # Основной цикл
    while True:
        try:
            current_time = datetime.now()
            current_minute = current_time.minute
            
            # Определяем интервал
            if current_minute % 5 == 0:  # Стоковая минута
                interval = 20
                mode = "⚡ ИНТЕНСИВНЫЙ"
            else:
                interval = 60
                mode = "🐌 ОБЫЧНЫЙ"
            
            logger.debug(f"{mode}: проверка каналов...")
            
            # Проверяем каждый канал по очереди
            for channel_id in DISCORD_CHANNEL_IDS:
                messages = get_discord_messages_simple(channel_id)
                if messages:
                    found = process_messages(messages)
                    if found:
                        logger.info("✅ Найдены семена!")
            
            logger.debug(f"💤 Ожидаю {interval} секунд...")
            time.sleep(interval)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторинге: {e}")
            time.sleep(60)

def telegram_poller():
    """Обработчик Telegram команд"""
    global telegram_offset
    
    time.sleep(10)
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {'offset': telegram_offset + 1, 'timeout': 10, 'limit': 1}
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok') and data.get('result'):
                    for update in data['result']:
                        telegram_offset = update['update_id']
                        
                        if 'message' in update:
                            msg = update['message']
                            chat_id = msg['chat']['id']
                            text = msg.get('text', '')
                            
                            if text == '/status':
                                uptime = datetime.now() - startup_time
                                hours = uptime.total_seconds() / 3600
                                
                                seeds_stats = "\n".join([
                                    f"{config['emoji']} {config['display_name']}: {count}"
                                    for name, config in TARGET_SEEDS.items()
                                    for count in [found_seeds_count.get(name, 0)]
                                ])
                                
                                status_msg = (
                                    f"📊 <b>Статус бота</b>\n\n"
                                    f"{bot_status}\n"
                                    f"⏰ Работает: {hours:.1f} часов\n"
                                    f"📡 Каналов: {len(DISCORD_CHANNEL_IDS)} шт\n"
                                    f"🎯 Отслеживаю: {BOT_NAME_TO_TRACK}\n"
                                    f"🏓 Самопинг: {ping_count} раз\n\n"
                                    f"🎯 <b>Найдено семян:</b>\n"
                                    f"{seeds_stats}"
                                )
                                
                                send_telegram_message(chat_id, status_msg)
            
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"❌ Ошибка Telegram: {e}")
            time.sleep(10)

@app.route('/')
def home():
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    return f"""
    <html>
        <head><title>🌱 Seed Monitor</title></head>
        <body>
            <h1>🌱 Мониторинг семян</h1>
            <p><strong>Статус:</strong> {bot_status}</p>
            <p><strong>Время работы:</strong> {hours:.1f} часов</p>
            <p><strong>Каналов Discord:</strong> {len(DISCORD_CHANNEL_IDS)}</p>
            <p><strong>Самопинг:</strong> {ping_count} раз</p>
        </body>
    </html>
    """

def start_background_threads():
    """Запускает фоновые потоки"""
    threads = [
        threading.Thread(target=monitor_discord_simple, daemon=True),
        threading.Thread(target=telegram_poller, daemon=True),
        threading.Thread(target=self_pinger, daemon=True)
    ]
    
    for thread in threads:
        thread.start()
    
    return threads

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК УПРОЩЕННОЙ ВЕРСИИ БОТА")
    logger.info(f"📡 Каналы: {len(DISCORD_CHANNEL_IDS)} шт")
    logger.info(f"🤖 Отслеживаю: {BOT_NAME_TO_TRACK}")
    
    # Тестируем подключение перед запуском
    connection_ok = test_discord_connection()
    
    if connection_ok:
        send_to_bot("✅ <b>Бот запущен!</b>\nУпрощенная версия с проверкой подключения.")
    else:
        send_to_bot("⚠️ <b>Внимание:</b> Проблемы с Discord. Бот запускается в тестовом режиме.")
    
    start_background_threads()
    app.run(host='0.0.0.0', port=5000)
