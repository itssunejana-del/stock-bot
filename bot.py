#!/usr/bin/env python3
"""
🚀 МОНИТОРИНГ KIRO (WebSocket + Python 3.10) + ТОМАТ 🍅
"""

import os
import discord
import requests
from flask import Flask
import threading
import time
from datetime import datetime
import sys
import logging

# ==================== НАСТРОЙКА ЛОГГИНГА ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== ПРОВЕРКА ВЕРСИИ ====================
print(f"🚀 Python: {sys.version}")

# ==================== НАСТРОЙКИ ====================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
SEEDS_CHANNEL_ID = os.getenv('SEEDS_CHANNEL_ID')

# Проверка
REQUIRED_VARS = ['DISCORD_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHANNEL_ID', 'SEEDS_CHANNEL_ID']
missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
if missing:
    logger.error(f'❌ Отсутствуют переменные: {missing}')
    exit(1)

logger.info(f"🌱 Канал Discord: {SEEDS_CHANNEL_ID}")
logger.info(f"📢 Канал Telegram: {TELEGRAM_CHANNEL_ID}")
logger.info(f"🤖 Бот Telegram: {TELEGRAM_BOT_CHAT_ID}")

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram(chat_id, text, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Telegram отправлено: {text[:50]}...")
            return True
        else:
            logger.error(f"❌ Telegram ошибка {response.status_code}: {response.text[:100]}")
            return False
    except Exception as e:
        logger.error(f'❌ Telegram error: {e}')
        return False

def send_telegram_sticker(chat_id, sticker_id):
    """Отправляет стикер в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {"chat_id": chat_id, "sticker": sticker_id}
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f'❌ Ошибка отправки стикера: {e}')
        return False

# ==================== КОНФИГУРАЦИЯ ПРЕДМЕТОВ ====================
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
        'keywords': ['tomato', 'томат', '🍅'],
        'sticker_id': "CAACAgIAAxkBAAEP1btpIXhIEvgVEK4c6ugJv1EgP7UY-wAChokAAtZpCElVMcRUgb_jdDYE",  # Временно тот же стикер
        'emoji': '🍅',
        'display_name': 'Tomato'
    }
}

# ==================== DISCORD БОТ ====================
class DiscordBot:
    def __init__(self):
        self.found_items = {name: 0 for name in TARGET_ITEMS.keys()}
        self.start_time = datetime.now()
        self.channel_enabled = True
        logger.info("🤖 Discord бот инициализирован")
        
    def run(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        
        client = discord.Client(intents=intents)
        
        @client.event
        async def on_ready():
            logger.info(f'✅ Discord бот {client.user} подключен через WebSocket!')
            
            # Стартовое сообщение
            if TELEGRAM_BOT_CHAT_ID:
                items_list = "\n".join([
                    f"{config['emoji']} {config['display_name']}" 
                    for config in TARGET_ITEMS.values()
                ])
                
                send_telegram(
                    TELEGRAM_BOT_CHAT_ID,
                    f"✅ <b>Мониторинг Kiro запущен с томатом! 🍅</b>\n\n"
                    f"🎯 <b>Отслеживаю 4 предмета:</b>\n"
                    f"{items_list}\n\n"
                    f"📢 <b>Канал:</b> {TELEGRAM_CHANNEL_ID}\n"
                    f"🌱 <b>Канал Discord:</b> {SEEDS_CHANNEL_ID}\n"
                    f"⏰ <b>Запущен:</b> {self.start_time.strftime('%H:%M:%S')}\n\n"
                    f"🤖 <b>WebSocket подключение активно</b>\n"
                    f"🍅 <b>Томат добавлен для тестирования</b>\n"
                    f"✅ Бот готов к работе!"
                )
        
        @client.event
        async def on_message(message):
            try:
                # Логируем все сообщения для отладки
                logger.debug(f"📨 Сообщение от {message.author}: {message.content}")
                
                # Пропускаем сообщения от самого бота
                if message.author == client.user:
                    return
                
                # Проверяем канал
                if str(message.channel.id) != SEEDS_CHANNEL_ID:
                    return
                
                logger.info(f"🔍 Проверяю сообщение в канале {SEEDS_CHANNEL_ID}")
                logger.info(f"👤 Автор: {message.author.name} (id: {message.author.id})")
                logger.info(f"📝 Содержимое: {message.content}")
                
                # Проверяем автора (ищем Kiro)
                if 'kiro' not in message.author.name.lower():
                    logger.debug(f"⏭️ Пропускаем - не Kiro: {message.author.name}")
                    return
                
                logger.info("✅ Это сообщение от Kiro!")
                
                # Извлекаем текст из сообщения
                text = message.content.lower() if message.content else ""
                
                # Добавляем текст из эмбедов
                for embed in message.embeds:
                    if embed.title:
                        text += " " + embed.title.lower()
                    if embed.description:
                        text += " " + embed.description.lower()
                    for field in embed.fields:
                        text += " " + field.name.lower()
                        text += " " + field.value.lower()
                
                logger.info(f"🔎 Полный текст для поиска: {text[:200]}...")
                
                # Ищем целевые предметы
                found_items_in_message = []
                
                for item_name, item_config in TARGET_ITEMS.items():
                    # Проверяем ключевые слова
                    for keyword in item_config['keywords']:
                        if keyword.lower() in text:
                            found_items_in_message.append(item_name)
                            logger.info(f"🎯 Найдено ключевое слово '{keyword}' для {item_name}")
                            break
                
                # Обрабатываем найденные предметы
                for item_name in found_items_in_message:
                    item_config = TARGET_ITEMS[item_name]
                    
                    # Увеличиваем счетчик
                    self.found_items[item_name] += 1
                    
                    # Время обнаружения
                    current_time = datetime.now().strftime('%H:%M:%S')
                    
                    # Логируем
                    logger.info(f"✅ Найден {item_config['emoji']} {item_config['display_name']} в {current_time}")
                    
                    # Отправляем уведомление в бота
                    if TELEGRAM_BOT_CHAT_ID:
                        notification = f"✅ Найден {item_config['emoji']} {item_config['display_name']} в {current_time}"
                        send_telegram(TELEGRAM_BOT_CHAT_ID, notification)
                    
                    # Отправляем стикер в канал (если включено)
                    if self.channel_enabled and item_config['sticker_id']:
                        sticker_sent = send_telegram_sticker(
                            TELEGRAM_CHANNEL_ID, 
                            item_config['sticker_id']
                        )
                        if sticker_sent:
                            logger.info(f"📢 Стикер {item_config['emoji']} отправлен в канал")
                
                if not found_items_in_message:
                    logger.info("📭 Ничего не найдено в сообщении")
                    
            except Exception as e:
                logger.error(f"💥 Ошибка обработки сообщения: {e}")
        
        @client.event
        async def on_error(event, *args, **kwargs):
            logger.error(f"⚠️ Discord ошибка в событии {event}: {args}")
        
        # Запускаем бота
        logger.info('🔗 Подключение к Discord через WebSocket...')
        client.run(DISCORD_TOKEN)

# ==================== FLASK СЕРВЕР ====================
app = Flask(__name__)
bot = DiscordBot()

@app.route('/')
def home():
    uptime = datetime.now() - bot.start_time
    uptime_str = str(uptime).split('.')[0]
    
    # Статистика найденных предметов
    stats = []
    for item_name, count in bot.found_items.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            stats.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    # HTML для отслеживаемых предметов
    tracked_items = []
    for item in TARGET_ITEMS.values():
        tracked_items.append(f"{item['emoji']} {item['display_name']}")
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>🌱 Мониторинг Kiro (WebSocket) 🍅</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            .card {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .status-ok {{ color: #2ecc71; font-weight: bold; }}
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
        <h1>🌱 Мониторинг Kiro (WebSocket) 🍅</h1>
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> <span class="status-ok">✅ WebSocket активен</span></p>
            <p><strong>Время работы:</strong> {uptime_str}</p>
            <p><strong>Канал Discord:</strong> {SEEDS_CHANNEL_ID}</p>
            <p><strong>Канал Telegram:</strong> {TELEGRAM_CHANNEL_ID}</p>
            <p><strong>Отправка стикеров:</strong> {'✅ ВКЛЮЧЕНА' if bot.channel_enabled else '⏸️ ВЫКЛЮЧЕНА'}</p>
        </div>
        
        <div class="card">
            <h2>🎯 Отслеживаемые предметы (4 предмета)</h2>
            <ul>{"".join([f'<li>{item}</li>' for item in tracked_items])}</ul>
            <p><em>🍅 Томат добавлен для тестирования!</em></p>
        </div>
        
        <div class="card">
            <h2>🏆 Найдено предметов</h2>
            <ul>{"".join([f'<li>{stat}</li>' for stat in stats]) if stats else '<li>Пока ничего не найдено</li>'}</ul>
        </div>
        
        <div class="card">
            <h2>🎛️ Управление</h2>
            <p>
                <a class="button" href="/enable">✅ Включить канал</a>
                <a class="button" href="/disable">⏸️ Выключить канал</a>
                <a class="button" href="/test">🍅 Тест томата</a>
            </p>
        </div>
        
        <div class="card">
            <h2>⚙️ Техническая информация</h2>
            <p><strong>Метод подключения:</strong> Discord WebSocket</p>
            <p><strong>Библиотека:</strong> disnake (аналог discord.py)</p>
            <p><strong>Python версия:</strong> 3.10.13</p>
            <p><strong>Запущен:</strong> {bot.start_time.strftime('%d.%m.%Y %H:%M:%S')}</p>
            <p><strong>Текущее время:</strong> {datetime.now().strftime('%H:%M:%S')}</p>
        </div>
        
        <div class="card">
            <h2>🔍 Для тестирования</h2>
            <p><strong>Отправь в Discord канал сообщение:</strong></p>
            <ul>
                <li><code>tomato</code> или <code>🍅</code> или <code>томат</code></li>
                <li><code>octobloom</code> или <code>октоблум</code></li>
                <li><code>zebrazinkle</code></li>
                <li><code>firework fern</code></li>
            </ul>
            <p>Бот должен отправить уведомление в Telegram!</p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': (datetime.now() - bot.start_time).total_seconds(),
        'found_items': bot.found_items,
        'channel_enabled': bot.channel_enabled,
        'python_version': '3.10.13',
        'tracking_items': len(TARGET_ITEMS),
        'discord_connected': True
    }

@app.route('/enable')
def enable():
    bot.channel_enabled = True
    return "✅ Отправка стикеров в канал включена"

@app.route('/disable')
def disable():
    bot.channel_enabled = False
    return "⏸️ Отправка стикеров в канал выключена"

@app.route('/test')
def test():
    """Тестовая страница для проверки работы"""
    if TELEGRAM_CHANNEL_ID:
        send_telegram(TELEGRAM_CHANNEL_ID, "🧪 <b>Тестовое сообщение от бота!</b>\nЕсли видишь это - бот работает!")
    return "✅ Тестовое сообщение отправлено в Telegram"

# ==================== ЗАПУСК ====================
def run_flask():
    """Запускает Flask сервер"""
    from waitress import serve
    port = int(os.getenv('PORT', 10000))
    logger.info(f'🌐 Веб-сервер запущен на порту {port}')
    serve(app, host='0.0.0.0', port=port)

if __name__ == '__main__':
    print('=' * 60)
    print('🚀 ЗАПУСК МОНИТОРИНГА KIRO С ТОМАТОМ 🍅')
    print('=' * 60)
    print(f'🌱 Канал Discord: {SEEDS_CHANNEL_ID}')
    print(f'📢 Канал Telegram: {TELEGRAM_CHANNEL_ID}')
    print(f'🤖 Бот Telegram: {TELEGRAM_BOT_CHAT_ID}')
    print(f'🎯 Отслеживаю: {len(TARGET_ITEMS)} предметов')
    print(f'🍅 Томат: ДА! (для тестирования)')
    print('=' * 60)
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Даем Flask время запуститься
    time.sleep(3)
    
    # Запускаем Discord бота
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("🛑 Остановка бота...")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        # Попытка перезапуска
        time.sleep(30)
        bot.run()
