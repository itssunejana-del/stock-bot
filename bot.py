#!/usr/bin/env python3
"""
🚀 МОНИТОРИНГ KIRO - СТАБИЛЬНАЯ ВЕРСИЯ
Самопинг как в старом коде + подробное логирование
"""

import os
import requests
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, jsonify
import logging

# ==================== НАСТРОЙКА ЛОГОВ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
# Все эти переменные должны быть в Render Environment
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')
BOT_NAME_TO_TRACK = os.getenv('BOT_NAME_TO_TRACK', 'kiro').lower()

# ID Discord каналов через запятую
CHANNELS_TO_MONITOR = {
    'seeds': os.getenv('SEEDS_CHANNEL_ID', ''),
    'eggs': os.getenv('EGGS_CHANNEL_ID', ''),
    'event_shop': os.getenv('EVENT_SHOP_CHANNEL_ID', ''),
    'pass_shop': os.getenv('PASS_SHOP_CHANNEL_ID', '')
}

# ==================== ОТСЛЕЖИВАЕМЫЕ ПРЕДМЕТЫ ====================
TARGET_ITEMS = {
    'octobloom': {
        'keywords': ['octobloom', 'октоблум'],
        'sticker_id': "CAACAgIAAxkBAAEP1btpIXhIEvgVEK4c6ugJv1EgP7UY-wAChokAAtZpCElVMcRUgb_jdDYE",
        'emoji': '🐙',
        'display_name': 'Octobloom'
    },
    'zebrazinkle': {
        'keywords': ['zebrazinkle', 'zebra zinkle'],
        'sticker_id': "CAACAgIAAxkBAAEPwjJpFDhW_6Vu29vF7DrTHFBcSf_WIAAC1XkAAkCXoUgr50G4SlzwrzYE",
        'emoji': '🦓',
        'display_name': 'Zebrazinkle'
    },
    'firework_fern': {
        'keywords': ['firework fern', 'fireworkfern'],
        'sticker_id': "CAACAgIAAxkBAAEQHChpUBeOda8Uf0Uwig6BwvkW_z1ndAAC5Y0AAl8dgEoandjqAtpRWTYE",
        'emoji': '🎆',
        'display_name': 'Firework Fern'
    },
    'tomato': {
        'keywords': ['tomato', 'томат', 'помидор'],
        'sticker_id': "",  # Добавьте ID стикера для томата
        'emoji': '🍅',
        'display_name': 'Tomato'
    }
}

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
bot_start_time = datetime.now()
last_processed_ids = {}
ping_count = 0
last_ping_time = None
discord_request_count = 0
last_discord_request = 0
found_items_count = {name: 0 for name in TARGET_ITEMS.keys()}
last_error = None
bot_status = "🟢 Инициализация"

# ==================== ПРОВЕРКА КОНФИГА ====================
def check_config():
    """Проверяет все настройки и выводит ошибки"""
    errors = []
    
    if not DISCORD_TOKEN:
        errors.append("❌ DISCORD_TOKEN не установлен")
    
    if not TELEGRAM_TOKEN:
        errors.append("❌ TELEGRAM_TOKEN не установлен")
    
    if not TELEGRAM_CHANNEL_ID:
        errors.append("❌ TELEGRAM_CHANNEL_ID не установлен")
    
    # Проверяем хотя бы один канал
    active_channels = [name for name, cid in CHANNELS_TO_MONITOR.items() if cid]
    if not active_channels:
        errors.append("❌ Не указаны ID Discord каналов")
    else:
        logger.info(f"✅ Мониторю каналы: {', '.join(active_channels)}")
    
    # Выводим все ошибки
    if errors:
        for error in errors:
            logger.error(error)
        return False
    
    logger.info("✅ Конфигурация проверена успешно")
    return True

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(text, parse_mode="HTML"):
    """Отправляет сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": text,
            "parse_mode": parse_mode
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

def send_telegram_sticker(sticker_id):
    """Отправляет стикер в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "sticker": sticker_id,
            "disable_notification": True
        }
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"❌ Ошибка отправки стикера: {e}")
        return False

# ==================== DISCORD ФУНКЦИИ ====================
def safe_fetch_discord_messages(channel_id, limit=2):
    """Безопасный запрос к Discord API"""
    global discord_request_count, last_discord_request, last_error
    
    if not DISCORD_TOKEN or not channel_id:
        logger.warning("⚠️ Нет токена или ID канала")
        return None
    
    try:
        # Защита от лимитов - минимум 5 секунд между запросами
        current_time = time.time()
        time_since_last = current_time - last_discord_request
        
        if time_since_last < 5:
            wait_time = 5 - time_since_last
            logger.debug(f"⏳ Защита от лимита: жду {wait_time:.1f} сек")
            time.sleep(wait_time)
        
        discord_request_count += 1
        last_discord_request = time.time()
        
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            messages = response.json()
            
            # Фильтруем сообщения только от Kiro
            kiro_messages = []
            for msg in messages:
                author = msg.get('author', {})
                username = author.get('username', '').lower()
                is_bot = author.get('bot', False)
                
                if (BOT_NAME_TO_TRACK in username) or (is_bot and BOT_NAME_TO_TRACK in username):
                    kiro_messages.append(msg)
            
            last_error = None
            return kiro_messages
            
        elif response.status_code == 429:
            retry_after = response.json().get('retry_after', 5.0)
            last_error = f"Discord лимит: {retry_after} сек"
            logger.warning(f"⏳ Discord API лимит. Жду {retry_after} сек.")
            time.sleep(retry_after + 1.0)
            return None
        else:
            last_error = f"Discord API ошибка: {response.status_code}"
            logger.error(f"❌ Ошибка Discord API {response.status_code}: {response.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        last_error = "Таймаут запроса к Discord"
        logger.warning("⏰ Таймаут запроса к Discord")
        return None
    except Exception as e:
        last_error = f"Ошибка Discord: {str(e)}"
        logger.error(f"❌ Ошибка Discord: {e}")
        return None

def extract_text_from_message(message):
    """Извлекает весь текст из сообщения Discord"""
    full_text = message.get('content', '').lower()
    
    for embed in message.get('embeds', []):
        if embed.get('title'):
            full_text += ' ' + embed.get('title', '').lower()
        if embed.get('description'):
            full_text += ' ' + embed.get('description', '').lower()
    
    return full_text

# ==================== МОНИТОРИНГ ====================
def check_channel(channel_name, channel_id):
    """Проверяет один канал Discord"""
    global last_processed_ids, found_items_count, bot_status
    
    if not channel_id:
        return False
    
    logger.debug(f"🔍 Проверяю {channel_name}...")
    
    messages = safe_fetch_discord_messages(channel_id, limit=2)
    if not messages:
        logger.debug(f"📭 В {channel_name} нет сообщений от {BOT_NAME_TO_TRACK}")
        return False
    
    found_items_in_check = []
    
    for message in messages:
        message_id = message['id']
        
        # Проверяем, не обрабатывали ли уже это сообщение
        last_id = last_processed_ids.get(channel_id)
        if last_id and int(message_id) <= int(last_id):
            continue
        
        # НОВОЕ сообщение!
        last_processed_ids[channel_id] = message_id
        text = extract_text_from_message(message)
        
        # Ищем предметы
        for item_name, item_config in TARGET_ITEMS.items():
            for keyword in item_config['keywords']:
                if keyword.lower() in text:
                    if item_name not in found_items_in_check:
                        found_items_count[item_name] += 1
                        found_items_in_check.append(item_name)
                    break
        
        break  # Обрабатываем только самое новое сообщение
    
    if found_items_in_check:
        logger.info(f"🎯 Найдены предметы в {channel_name}: {', '.join(found_items_in_check)}")
        
        for item_name in found_items_in_check:
            item_config = TARGET_ITEMS[item_name]
            current_time = datetime.now().strftime('%H:%M:%S')
            notification = f"✅ Найден {item_config['emoji']} {item_config['display_name']} в {current_time}"
            
            # Отправляем в Telegram
            if send_telegram_message(notification):
                logger.info(f"📱 Уведомление отправлено: {item_config['display_name']}")
            else:
                logger.error(f"❌ Не удалось отправить уведомление о {item_config['display_name']}")
            
            # Отправляем стикер (если есть)
            if item_config.get('sticker_id'):
                if send_telegram_sticker(item_config['sticker_id']):
                    logger.info(f"✅ Стикер {item_config['emoji']} отправлен")
                else:
                    logger.error(f"❌ Ошибка отправки стикера {item_config['emoji']}")
        
        bot_status = f"🟢 Найдены предметы в {channel_name}"
        return True
    
    logger.debug(f"📭 {BOT_NAME_TO_TRACK} в {channel_name} без нужных предметов")
    bot_status = f"🟢 Проверен {channel_name}"
    return False

def monitor_channels():
    """Главный цикл мониторинга"""
    logger.info("🚀 Запуск мониторинга каналов...")
    
    while True:
        try:
            # Проверяем все каналы
            for channel_name, channel_id in CHANNELS_TO_MONITOR.items():
                if channel_id:  # Проверяем только если ID указан
                    check_channel(channel_name, channel_id)
            
            # Ждем 30 секунд перед следующей проверкой
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторинге: {e}")
            time.sleep(30)

# ==================== САМОПИНГ ====================
def self_pinger():
    """Самопинг чтобы Render не останавливал сервис"""
    global ping_count, last_ping_time
    
    logger.info("🏓 Запуск самопинга (каждые 8 минут)")
    
    time.sleep(10)  # Ждем запуска
    
    while True:
        try:
            ping_count += 1
            last_ping_time = datetime.now()
            logger.info(f"🏓 Самопинг #{ping_count}...")
            
            response = requests.get(f"{RENDER_SERVICE_URL}/health", timeout=10)
            if response.status_code == 200:
                logger.info("✅ Самопинг успешен - сервис активен")
            else:
                logger.warning(f"⚠️ Самопинг: статус {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
        
        logger.info("💤 Ожидаю 8 минут до следующего самопинга...")
        time.sleep(480)  # 8 минут

# ==================== FLASK СЕРВЕР ====================
app = Flask(__name__)

@app.route('/')
def home():
    """Главная страница с подробной информацией"""
    uptime = datetime.now() - bot_start_time
    hours = uptime.total_seconds() / 3600
    
    items_stats = []
    for item_name, count in found_items_count.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            items_stats.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    active_channels = []
    for name, cid in CHANNELS_TO_MONITOR.items():
        if cid:
            last_id = last_processed_ids.get(cid, 'Еще не было')
            active_channels.append(f"{name}: {last_id}")
    
    return f"""
    <html>
    <head>
        <title>🌱 Мониторинг Kiro + Tomato 🍅</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .card {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .status-ok {{ color: #2ecc71; }} .status-error {{ color: #e74c3c; }}
        </style>
    </head>
    <body>
        <h1>🌱 Мониторинг Kiro + Tomato 🍅</h1>
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> <span class="status-ok">{bot_status}</span></p>
            <p><strong>Время работы:</strong> {hours:.1f} часов</p>
            <p><strong>Запросов к Discord:</strong> {discord_request_count}</p>
            <p><strong>Самопингов:</strong> {ping_count}</p>
            <p><strong>Отслеживаю бота:</strong> {BOT_NAME_TO_TRACK}</p>
        </div>
        
        <div class="card">
            <h2>🎯 Отслеживаемые предметы</h2>
            <ul>
                <li>🐙 Octobloom</li>
                <li>🦓 Zebrazinkle</li>
                <li>🎆 Firework Fern</li>
                <li>🍅 Tomato (новый!)</li>
            </ul>
        </div>
        
        <div class="card">
            <h2>📊 Найдено предметов</h2>
            <ul>{''.join([f'<li>{stat}</li>' for stat in items_stats]) if items_stats else '<li>Еще не найдено</li>'}</ul>
        </div>
        
        <div class="card">
            <h2>📝 Мониторинг каналов</h2>
            <ul>{''.join([f'<li>{channel}</li>' for channel in active_channels])}</ul>
        </div>
        
        <div class="card">
            <h2>⚠️ Последняя ошибка</h2>
            <p><code>{last_error if last_error else 'Ошибок нет'}</code></p>
        </div>
        
        <div class="card">
            <h2>🔄 Частота проверок</h2>
            <p><strong>Проверка каналов:</strong> каждые 30 секунд</p>
            <p><strong>Самопинг:</strong> каждые 8 минут</p>
            <p><strong>Защита Discord:</strong> 5 секунд между запросами</p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    """Эндпоинт для проверки здоровья"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': (datetime.now() - bot_start_time).total_seconds(),
        'discord_requests': discord_request_count,
        'ping_count': ping_count,
        'last_error': last_error,
        'items_found': found_items_count
    })

@app.route('/test')
def test():
    """Тестовый эндпоинт для проверки"""
    return jsonify({
        'message': 'Bot is working!',
        'config_ok': check_config(),
        'channels': {k: bool(v) for k, v in CHANNELS_TO_MONITOR.items()}
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    # Проверяем конфигурацию
    if not check_config():
        logger.error("❌ Невозможно запустить бота из-за ошибок конфигурации")
        exit(1)
    
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК МОНИТОРИНГА KIRO С TOMATO")
    logger.info("=" * 60)
    logger.info(f"🎯 Отслеживаю предметы: {', '.join([item['display_name'] for item in TARGET_ITEMS.values()])}")
    logger.info(f"🤖 Слежу за ботом: {BOT_NAME_TO_TRACK}")
    logger.info("⏰ Частота проверок: каждые 30 секунд")
    logger.info("🏓 Самопинг: каждые 8 минут")
    logger.info("=" * 60)
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=monitor_channels, daemon=True)
    monitor_thread.start()
    
    # Запускаем самопинг в отдельном потоке
    pinger_thread = threading.Thread(target=self_pinger, daemon=True)
    pinger_thread.start()
    
    # Отправляем стартовое сообщение в Telegram
    start_message = (
        f"✅ <b>Мониторинг Kiro запущен!</b>\n\n"
        f"📊 <b>Отслеживаю:</b>\n"
        f"• 🐙 Octobloom\n"
        f"• 🦓 Zebrazinkle\n"
        f"• 🎆 Firework Fern\n"
        f"• 🍅 Tomato (новый!)\n\n"
        f"🤖 <b>Слежу за ботом:</b> {BOT_NAME_TO_TRACK}\n"
        f"⏰ <b>Проверка:</b> каждые 30 секунд\n"
        f"🏓 <b>Самопинг:</b> каждые 8 минут\n\n"
        f"<i>Бот готов к работе!</i>"
    )
    send_telegram_message(start_message)
    
    # Запускаем Flask сервер
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    
    # Используем waitress для продакшена
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port)
    except ImportError:
        logger.warning("⚠️ Waitress не установлен, использую dev-сервер")
        app.run(host='0.0.0.0', port=port, debug=False)
