#!/usr/bin/env python3
"""
🚀 МОНИТОРИНГ KIRO (Стабильный WebSocket + Самопинг)
"""

import os
import disnake as discord
import requests
from flask import Flask
import threading
import time
from datetime import datetime
import sys
import logging
import asyncio

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
RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')

# Проверка
REQUIRED_VARS = ['DISCORD_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHANNEL_ID', 'SEEDS_CHANNEL_ID']
missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
if missing:
    logger.error(f'❌ Отсутствуют переменные: {missing}')
    exit(1)

logger.info(f"🌱 Канал Discord: {SEEDS_CHANNEL_ID}")
logger.info(f"📢 Канал Telegram: {TELEGRAM_CHANNEL_ID}")
logger.info(f"🤖 Бот Telegram: {TELEGRAM_BOT_CHAT_ID}")

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
bot_start_time = datetime.now()
ping_count = 0
last_ping_time = None
found_items_count = {
    'octobloom': 0,
    'zebrazinkle': 0, 
    'firework_fern': 0,
    'tomato': 0
}
discord_client = None

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram(chat_id, text, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Telegram отправлено: {text[:50]}...")
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram, жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Telegram ошибка {response.status_code}: {response.text[:100]}")
            return False
    except Exception as e:
        logger.error(f'❌ Telegram error: {e}')
        return False

def send_to_bot(text):
    """Отправляет сообщение в личку бота"""
    if TELEGRAM_BOT_CHAT_ID:
        return send_telegram(TELEGRAM_BOT_CHAT_ID, text)
    return False

def send_to_channel(text):
    """Отправляет сообщение в Telegram канал"""
    if TELEGRAM_CHANNEL_ID:
        return send_telegram(TELEGRAM_CHANNEL_ID, text)
    return False

# ==================== КОНФИГУРАЦИЯ ПРЕДМЕТОВ ====================
TARGET_ITEMS = {
    'octobloom': {
        'keywords': ['octobloom', 'октоблум'],
        'emoji': '🐙',
        'display_name': 'Octobloom'
    },
    'zebrazinkle': {
        'keywords': ['zebrazinkle', 'zebra zinkle'],
        'emoji': '🦓',
        'display_name': 'Zebrazinkle'
    },
    'firework_fern': {
        'keywords': ['firework fern', 'fireworkfern'],
        'emoji': '🎆',
        'display_name': 'Firework Fern'
    },
    'tomato': {
        'keywords': ['tomato', 'томат', '🍅'],
        'emoji': '🍅',
        'display_name': 'Tomato'
    }
}

# ==================== САМОПИНГ ====================
def self_pinger():
    """Самопинг каждые 8 минут чтобы Render не останавливал сервис"""
    global ping_count, last_ping_time
    
    logger.info("🏓 Запуск самопинга (каждые 8 минут)")
    
    time.sleep(30)  # Ждем запуска Flask
    
    while True:
        try:
            ping_count += 1
            last_ping_time = datetime.now()
            
            # Пингуем свой же сервис
            response = requests.get(f"{RENDER_SERVICE_URL}/health", timeout=10)
            
            if response.status_code == 200:
                logger.info(f"🏓 Самопинг #{ping_count} успешен")
                
                # Раз в 10 пингов отправляем статус
                if ping_count % 10 == 0:
                    uptime = datetime.now() - bot_start_time
                    hours = uptime.total_seconds() / 3600
                    status = (
                        f"📊 <b>Статус самопинга #{ping_count}</b>\n"
                        f"⏰ Работает: {hours:.1f} часов\n"
                        f"🕒 Последний пинг: {last_ping_time.strftime('%H:%M:%S')}\n"
                        f"✅ WebSocket активен\n"
                        f"🎯 Найдено томатов: {found_items_count['tomato']}"
                    )
                    send_to_bot(status)
            else:
                logger.warning(f"⚠️ Самопинг: статус {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
            # Отправляем ошибку в Telegram
            error_msg = f"⚠️ <b>Ошибка самопинга:</b>\n<code>{str(e)[:200]}</code>"
            send_to_bot(error_msg)
        
        # Ждем 8 минут
        logger.info("💤 Ожидаю 8 минут до следующего самопинга...")
        time.sleep(480)

# ==================== DISCORD БОТ ====================
def run_discord_bot():
    """Запускает Discord бота в отдельном потоке"""
    global discord_client
    
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    
    discord_client = discord.Client(intents=intents)
    
    @discord_client.event
    async def on_ready():
        logger.info(f'✅ Discord бот {discord_client.user} подключен через WebSocket!')
        
        # Стартовое сообщение
        items_list = "\n".join([
            f"{config['emoji']} {config['display_name']}" 
            for config in TARGET_ITEMS.values()
        ])
        
        send_to_bot(
            f"✅ <b>Мониторинг Kiro запущен!</b>\n\n"
            f"🎯 <b>Отслеживаю 4 предмета:</b>\n"
            f"{items_list}\n\n"
            f"📢 Канал: {TELEGRAM_CHANNEL_ID}\n"
            f"🌱 Канал Discord: {SEEDS_CHANNEL_ID}\n"
            f"⏰ Запущен: {bot_start_time.strftime('%H:%M:%S')}\n\n"
            f"🤖 WebSocket подключение активно\n"
            f"🏓 Самопинг каждые 8 минут\n"
            f"✅ Бот готов к работе!"
        )
    
    @discord_client.event
    async def on_message(message):
        try:
            # Пропускаем сообщения от самого бота
            if message.author == discord_client.user:
                return
            
            # Проверяем канал
            if str(message.channel.id) != SEEDS_CHANNEL_ID:
                return
            
            # Проверяем автора (ищем Kiro)
            if 'kiro' not in message.author.name.lower():
                return
            
            logger.info(f"📨 Сообщение от Kiro")
            
            # Извлекаем текст
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
            
            logger.info(f"🔍 Текст для поиска: {text[:200]}...")
            
            # Ищем предметы
            found_items = []
            for item_name, item_config in TARGET_ITEMS.items():
                for keyword in item_config['keywords']:
                    if keyword.lower() in text:
                        found_items.append(item_name)
                        logger.info(f"🎯 Найдено ключевое слово: {keyword}")
                        break
            
            # Обрабатываем найденные предметы
            for item_name in found_items:
                item_config = TARGET_ITEMS[item_name]
                found_items_count[item_name] += 1
                
                current_time = datetime.now().strftime('%H:%M:%S')
                
                # Логируем
                logger.info(f"✅ Найден {item_config['emoji']} {item_config['display_name']} в {current_time}")
                
                # Отправляем в Telegram канал
                message_text = f"{item_config['emoji']} <b>{item_config['display_name']}</b> найден в {current_time}"
                send_to_channel(message_text)
                
                # Отправляем в личку бота
                send_to_bot(f"✅ {item_config['emoji']} {item_config['display_name']} в {current_time}")
                
        except Exception as e:
            logger.error(f"💥 Ошибка обработки сообщения: {e}")
            error_msg = f"⚠️ <b>Ошибка обработки сообщения:</b>\n<code>{str(e)[:200]}</code>"
            send_to_bot(error_msg)
    
    @discord_client.event
    async def on_disconnect():
        logger.warning("⚠️ Discord WebSocket отключен")
        send_to_bot("⚠️ <b>Discord WebSocket отключен</b>")
    
    @discord_client.event 
    async def on_resumed():
        logger.info("✅ Discord WebSocket восстановлен")
        send_to_bot("✅ <b>Discord WebSocket восстановлен</b>")
    
    @discord_client.event
    async def on_error(event, *args, **kwargs):
        logger.error(f"⚠️ Discord ошибка: {event}")
    
    # Запускаем бота
    logger.info('🔗 Подключение к Discord через WebSocket...')
    discord_client.run(DISCORD_TOKEN)

# ==================== ФУНКЦИЯ ПЕРЕЗАПУСКА DISCORD ====================
def restart_discord_bot():
    """Перезапускает Discord бота при ошибках"""
    while True:
        try:
            run_discord_bot()
        except KeyboardInterrupt:
            logger.info("🛑 Остановка Discord бота")
            break
        except Exception as e:
            logger.error(f"💥 Ошибка Discord бота: {e}")
            send_to_bot(f"🚨 <b>Ошибка Discord бота:</b>\n<code>{str(e)[:200]}</code>\n\n🔄 Перезапуск через 30 секунд...")
            time.sleep(30)
            logger.info("🔄 Перезапуск Discord бота...")

# ==================== FLASK СЕРВЕР ====================
app = Flask(__name__)

@app.route('/')
def home():
    uptime = datetime.now() - bot_start_time
    uptime_str = str(uptime).split('.')[0]
    
    stats = []
    for item_name, count in found_items_count.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            stats.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    discord_status = "✅ Активен" if discord_client and discord_client.is_ready() else "❌ Отключен"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>🌱 Мониторинг Kiro 🍅</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            .card {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .status-ok {{ color: #2ecc71; font-weight: bold; }}
            .status-error {{ color: #e74c3c; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>🌱 Мониторинг Kiro 🍅</h1>
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> <span class="{'status-ok' if discord_client and discord_client.is_ready() else 'status-error'}">{discord_status}</span></p>
            <p><strong>Время работы:</strong> {uptime_str}</p>
            <p><strong>Самопингов:</strong> {ping_count}</p>
            <p><strong>Последний пинг:</strong> {last_ping_time.strftime('%H:%M:%S') if last_ping_time else 'Еще не было'}</p>
            <p><strong>WebSocket:</strong> {discord_status}</p>
        </div>
        
        <div class="card">
            <h2>🎯 Отслеживаемые предметы</h2>
            <ul>
                <li>🐙 Octobloom</li>
                <li>🦓 Zebrazinkle</li>
                <li>🎆 Firework Fern</li>
                <li>🍅 Tomato (для теста)</li>
            </ul>
        </div>
        
        <div class="card">
            <h2>🏆 Найдено предметов</h2>
            <ul>{"".join([f'<li>{stat}</li>' for stat in stats]) if stats else '<li>Пока ничего не найдено</li>'}</ul>
        </div>
        
        <div class="card">
            <h2>⚙️ Техническая информация</h2>
            <p><strong>Метод:</strong> WebSocket (disnake)</p>
            <p><strong>Python:</strong> 3.10.13</p>
            <p><strong>Самопинг:</strong> Каждые 8 минут</p>
            <p><strong>Автопереподключение:</strong> Да (через 30 сек)</p>
            <p><strong>Уведомления:</strong> Текст в Telegram</p>
            <p><strong>Логи ошибок:</strong> Отправляются в Telegram</p>
        </div>
        
        <div class="card">
            <h2>🔍 Последние логи</h2>
            <p><strong>Томатов найдено сегодня:</strong> {found_items_count['tomato']}</p>
            <p><strong>Последняя активность:</strong> {datetime.now().strftime('%H:%M:%S')}</p>
            <p><a href="/health">Детальный статус</a> | <a href="/test">Тест работы</a></p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    discord_ready = discord_client.is_ready() if discord_client else False
    return {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': (datetime.now() - bot_start_time).total_seconds(),
        'ping_count': ping_count,
        'found_items': found_items_count,
        'discord_connected': discord_ready,
        'discord_user': str(discord_client.user) if discord_client else None,
        'python_version': '3.10.13',
        'service_url': RENDER_SERVICE_URL
    }

@app.route('/test')
def test():
    """Тестовая страница"""
    send_to_bot("🧪 <b>Тест от бота!</b>\nЕсли видишь это - бот работает!")
    send_to_channel("🧪 <b>Тест в канал!</b>\nБот активен и мониторит стоки.")
    return "✅ Тестовые сообщения отправлены в Telegram"

# ==================== ЗАПУСК ====================
def run_flask():
    """Запускает Flask сервер"""
    from waitress import serve
    port = int(os.getenv('PORT', 10000))
    logger.info(f'🌐 Веб-сервер запущен на порту {port}')
    serve(app, host='0.0.0.0', port=port)

if __name__ == '__main__':
    print('=' * 60)
    print('🚀 ЗАПУСК МОНИТОРИНГА KIRO С САМОПИНГОМ')
    print('=' * 60)
    print(f'🌱 Канал Discord: {SEEDS_CHANNEL_ID}')
    print(f'📢 Канал Telegram: {TELEGRAM_CHANNEL_ID}')
    print(f'🤖 Бот Telegram: {TELEGRAM_BOT_CHAT_ID}')
    print('🎯 Отслеживаю: 4 предмета (включая томат)')
    print('🏓 Самопинг: каждые 8 минут')
    print('🔄 Автопереподключение: при ошибках')
    print('=' * 60)
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Даем Flask время запуститься
    time.sleep(3)
    
    # Запускаем самопинг в отдельном потоке
    ping_thread = threading.Thread(target=self_pinger, daemon=True)
    ping_thread.start()
    
    # Запускаем Discord бота в отдельном потоке с автоперезапуском
    discord_thread = threading.Thread(target=restart_discord_bot, daemon=True)
    discord_thread.start()
    
    # Держим основной поток активным
    try:
        while True:
            time.sleep(60)
            # Каждую минуту проверяем статус
            if discord_client and discord_client.is_ready():
                logger.debug("✅ Discord бот активен")
    except KeyboardInterrupt:
        logger.info("🛑 Остановка приложения...")
