#!/usr/bin/env python3
"""
🚀 МОНИТОРИНГ ДЛЯ НОВОЙ ИГРЫ (два канала: стоки + новости)
"""

import os
import disnake as discord
import requests
from flask import Flask, jsonify
import threading
import time
from datetime import datetime
import sys
import logging
import html

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
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')

# НОВЫЕ ПЕРЕМЕННЫЕ:
STOCKS_CHANNEL_ID = os.getenv('STOCKS_CHANNEL_ID')           # ID канала со стоками
STOCKS_TELEGRAM_CHANNEL = os.getenv('STOCKS_TELEGRAM_CHANNEL')  # Куда отправлять стикеры
NEWS_CHANNEL_ID = os.getenv('NEWS_CHANNEL_ID')               # ID новостного канала
NEWS_TELEGRAM_CHANNEL = os.getenv('NEWS_TELEGRAM_CHANNEL')   # Куда отправлять новости

# Обязательные переменные
REQUIRED_VARS = ['DISCORD_TOKEN', 'TELEGRAM_TOKEN', 'STOCKS_CHANNEL_ID', 'STOCKS_TELEGRAM_CHANNEL']
missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
if missing:
    logger.error(f'❌ Отсутствуют обязательные переменные: {missing}')
    exit(1)

# Проверяем новостной канал (опционально)
if os.getenv('NEWS_CHANNEL_ID') and not os.getenv('NEWS_TELEGRAM_CHANNEL'):
    logger.error('❌ Указан NEWS_CHANNEL_ID, но нет NEWS_TELEGRAM_CHANNEL')
    exit(1)

logger.info(f"📦 Канал стоков: {STOCKS_CHANNEL_ID}")
logger.info(f"📢 Telegram для стоков: {STOCKS_TELEGRAM_CHANNEL}")
if NEWS_CHANNEL_ID and NEWS_TELEGRAM_CHANNEL:
    logger.info(f"📰 Канал новостей: {NEWS_CHANNEL_ID}")
    logger.info(f"📢 Telegram для новостей: {NEWS_TELEGRAM_CHANNEL}")
logger.info(f"🤖 Бот Telegram: {TELEGRAM_BOT_CHAT_ID}")

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
bot_start_time = datetime.now()
ping_count = 0
last_ping_time = None
found_items_count = {}
processed_messages = set()
MAX_CACHE_SIZE = 50
discord_connected = False  # Флаг для отслеживания подключения к Discord

# ==================== КОНФИГУРАЦИЯ ПРЕДМЕТОВ ====================
TARGET_ITEMS = {
    'cherry': {
        'keywords': ['cherry', 'cherry seed', '🍒'],
        'sticker_id': "CAACAgIAAxkBAAEQnoFpnyHlfKoDssWIpZHbKrjgBUkgAQACy5AAAv894EjYncv41k4_XzoE",
        'emoji': '🍒',
        'display_name': 'Cherry'
    },
    'cabbage': {
        'keywords': ['cabbage', 'cabbage seed', '🥬'],
        'sticker_id': "CAACAgIAAxkBAAEQnoNpnyHvhLutfLJmqqqqk8_TWy-8wAACZ5YAAho06UipuXAdrrQYXToE",
        'emoji': '🥬',
        'display_name': 'Cabbage'
    },
    'super_sprinkler': {
        'keywords': ['super sprinkler'],  # Только точная фраза
        'sticker_id': "CAACAgIAAxkBAAEQnoVpnyH24p9XG865neBZzotLJBqyTwACzp0AAtmT-UgP-Ruhrq3S3joE",
        'emoji': '💧',
        'display_name': 'Super Sprinkler'
    },
    'bamboo': {
        'keywords': ['bamboo', 'bamboo seed', '🎋'],
        'sticker_id': "CAACAgIAAxkBAAEQnodpnyH9bW44AZ7HvDx91cIfEme3BQACrZgAAhHm6EgK9xH9AAGaNgAEOA",
        'emoji': '🎋',
        'display_name': 'Bamboo'
    },
    'mango': {
        'keywords': ['mango', 'mango seed', '🥭'],
        'sticker_id': "CAACAgIAAxkBAAEQnolpnyH_9X07Hw-t9R-WxqI5lVyy8gACxJgAAl-l6EhRDP07L99KwzgE",
        'emoji': '🥭',
        'display_name': 'Mango'
    }
}

# Инициализируем счетчики
for item_name in TARGET_ITEMS.keys():
    found_items_count[item_name] = 0

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram(chat_id, text, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Telegram отправлено в {chat_id}")
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

def send_telegram_sticker(chat_id, sticker_id):
    """Отправляет стикер в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {"chat_id": chat_id, "sticker": sticker_id}
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            logger.info(f"📢 Стикер отправлен в канал")
            return True
        else:
            logger.error(f"❌ Ошибка отправки стикера: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f'❌ Ошибка отправки стикера: {e}')
        return False

# ==================== ИЗВЛЕЧЕНИЕ ТЕКСТА ====================
def extract_full_content(message):
    """Извлекает весь текст из сообщения Discord"""
    full_content = ""
    
    # 1. Текст сообщения
    if message.content:
        full_content += f"{message.content}\n\n"
    
    # 2. Эмбеды
    if message.embeds:
        for embed in message.embeds:
            if embed.title:
                full_content += f"{embed.title}\n"
            if embed.description:
                full_content += f"{embed.description}\n"
            if embed.fields:
                for field in embed.fields:
                    full_content += f"\n{field.name}\n{field.value}\n"
            if embed.footer and embed.footer.text:
                full_content += f"\n{embed.footer.text}\n"
    
    # 3. Очистка
    import re
    full_content = re.sub(r'<:[^:]+:\d+>', '', full_content)
    full_content = re.sub(r'\*\*', '', full_content)
    full_content = html.escape(full_content)
    full_content = '\n'.join([line.strip() for line in full_content.split('\n') if line.strip()])
    
    return full_content.strip()

# ==================== САМОПИНГ ====================
def self_pinger():
    global ping_count, last_ping_time, discord_connected
    
    logger.info("🏓 Запуск самопинга (каждые 8 минут)")
    time.sleep(30)
    
    while True:
        try:
            ping_count += 1
            last_ping_time = datetime.now()
            
            try:
                response = requests.get(f"{RENDER_SERVICE_URL}/health", timeout=15)
                if response.status_code == 200:
                    logger.info(f"🏓 Самопинг #{ping_count} успешен")
                    
                    if ping_count % 10 == 0:
                        uptime = datetime.now() - bot_start_time
                        hours = uptime.total_seconds() / 3600
                        
                        stats = []
                        for item_name, count in found_items_count.items():
                            if count > 0:
                                item = TARGET_ITEMS[item_name]
                                stats.append(f"{item['emoji']} {item['display_name']}: {count}")
                        
                        stats_text = "\n".join(stats) if stats else "Пока ничего не найдено"
                        
                        discord_status = "✅ Подключен" if discord_connected else "❌ Отключен"
                        
                        status = (
                            f"📊 <b>Статус самопинга #{ping_count}</b>\n"
                            f"⏰ Работает: {hours:.1f} часов\n"
                            f"🕒 Последний пинг: {last_ping_time.strftime('%H:%M:%S')}\n"
                            f"🔗 Discord: {discord_status}\n"
                            f"📊 Обработано сообщений: {len(processed_messages)}\n\n"
                            f"🏆 <b>Найдено предметов:</b>\n"
                            f"{stats_text}"
                        )
                        send_to_bot(status)
                else:
                    logger.warning(f"⚠️ Самопинг: статус {response.status_code}")
                    
            except requests.exceptions.Timeout:
                logger.warning("⏰ Таймаут самопинга")
            except requests.exceptions.ConnectionError:
                logger.warning("🔌 Ошибка соединения при самопинге")
            except Exception as e:
                logger.error(f"❌ Ошибка запроса самопинга: {e}")
            
            logger.info("💤 Ожидаю 8 минут до следующего самопинга...")
            time.sleep(480)
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в самопинге: {e}")
            logger.info("🔄 Перезапуск самопинга через 30 секунд...")
            time.sleep(30)
            continue

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
    
    news_status = "✅ Подключен" if NEWS_CHANNEL_ID else "❌ Не настроен"
    discord_status = "✅ Подключен" if discord_connected else "❌ Отключен (IP бан)"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>🎮 Мониторинг новой игры</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            .card {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .status-ok {{ color: #2ecc71; font-weight: bold; }}
            .status-error {{ color: #e74c3c; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>🎮 Мониторинг новой игры</h1>
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> <span class="status-ok">✅ Flask работает</span></p>
            <p><strong>Discord:</strong> <span class="{'status-ok' if discord_connected else 'status-error'}">{discord_status}</span></p>
            <p><strong>Время работы:</strong> {uptime_str}</p>
            <p><strong>Самопингов:</strong> {ping_count}</p>
            <p><strong>Обработано сообщений:</strong> {len(processed_messages)}</p>
        </div>
        
        <div class="card">
            <h2>📦 Каналы мониторинга</h2>
            <p><strong>Стоки:</strong> {STOCKS_CHANNEL_ID}</p>
            <p><strong>Новости:</strong> {NEWS_CHANNEL_ID or 'Не настроен'} ({news_status})</p>
        </div>
        
        <div class="card">
            <h2>🎯 Отслеживаемые предметы</h2>
            <ul>
                <li>🍒 Cherry</li>
                <li>🥬 Cabbage</li>
                <li>💧 Super Sprinkler (только точное совпадение)</li>
                <li>🎋 Bamboo</li>
                <li>🥭 Mango</li>
            </ul>
            <p><em>📨 В канал: стикер<br>🤖 В бота: полный сток</em></p>
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
            <p><strong>Защита от дублей:</strong> Да (кеш 50 сообщений)</p>
            <p><strong>Уведомления:</strong> Стикеры в канал + полные логи в бота + новости</p>
        </div>
        
        <div class="card">
            <h2>🔍 Тестирование</h2>
            <p><a href="/health">Статус здоровья</a> | <a href="/test">Тест бота</a> | <a href="/ping">Ping</a> | <a href="/debug">Debug</a></p>
            <p><em>Сайт работает даже если Discord не подключен!</em></p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': (datetime.now() - bot_start_time).total_seconds(),
        'ping_count': ping_count,
        'found_items': found_items_count,
        'processed_messages': len(processed_messages),
        'discord_connected': discord_connected,
        'python_version': '3.10.13',
        'service_url': RENDER_SERVICE_URL,
        'channels': {
            'stocks': STOCKS_CHANNEL_ID,
            'news': NEWS_CHANNEL_ID
        }
    }

@app.route('/test')
def test():
    send_to_bot("🧪 <b>Тест от бота!</b>\nЕсли видишь это - бот работает!")
    return "✅ Тестовое сообщение отправлено в бота"

# ==================== ТЕСТОВЫЕ ЭНДПОИНТЫ ====================
@app.route('/ping')
def ping():
    """Проверка, работает ли Flask"""
    return "pong"

@app.route('/debug')
def debug():
    """Проверка переменных окружения"""
    import os
    return jsonify({
        'status': 'debug',
        'has_discord_token': bool(os.getenv('DISCORD_TOKEN')),
        'has_telegram_token': bool(os.getenv('TELEGRAM_TOKEN')),
        'stocks_channel': os.getenv('STOCKS_CHANNEL_ID'),
        'stocks_telegram': os.getenv('STOCKS_TELEGRAM_CHANNEL'),
        'news_channel': os.getenv('NEWS_CHANNEL_ID'),
        'news_telegram': os.getenv('NEWS_TELEGRAM_CHANNEL'),
        'bot_chat_id': os.getenv('TELEGRAM_BOT_CHAT_ID'),
        'render_service_url': os.getenv('RENDER_SERVICE_URL')
    })

# ==================== ЗАПУСК FLASK ====================
def run_flask():
    from waitress import serve
    port = int(os.getenv('PORT', 10000))
    logger.info(f'🌐 Веб-сервер запущен на порту {port}')
    serve(app, host='0.0.0.0', port=port)

# ==================== ЗАПУСК DISCORD БОТА ====================
def run_discord_bot():
    global discord_connected
    
    try:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        
        client = discord.Client(intents=intents)
        
        @client.event
        async def on_ready():
            global discord_connected
            discord_connected = True
            logger.info(f'✅ Discord бот {client.user} подключен!')
            
            items_list = "\n".join([
                f"{config['emoji']} {config['display_name']}" 
                for config in TARGET_ITEMS.values()
            ])
            
            msg = (
                f"✅ <b>Мониторинг новой игры запущен!</b>\n\n"
                f"🎯 <b>Отслеживаю:</b>\n{items_list}\n\n"
                f"📦 Канал стоков: {STOCKS_CHANNEL_ID}\n"
            )
            if NEWS_CHANNEL_ID:
                msg += f"📰 Канал новостей: {NEWS_CHANNEL_ID}\n"
            msg += f"⏰ Запущен: {bot_start_time.strftime('%H:%M:%S')}\n\n✅ Бот готов!"
            
            send_to_bot(msg)
        
        @client.event
        async def on_message(message):
            try:
                global processed_messages
                
                if message.author == client.user:
                    return
                
                channel_id = str(message.channel.id)
                
                # ===== НОВОСТНОЙ КАНАЛ =====
                if NEWS_CHANNEL_ID and channel_id == NEWS_CHANNEL_ID:
                    # Защита от дублей
                    if message.id in processed_messages:
                        return
                    
                    processed_messages.add(message.id)
                    if len(processed_messages) > MAX_CACHE_SIZE:
                        processed_messages.remove(next(iter(processed_messages)))
                    
                    logger.info(f"📰 Новость в канале {channel_id}")
                    
                    # Отправляем текст в Telegram
                    if NEWS_TELEGRAM_CHANNEL:
                        news_text = message.content if message.content else "📄 Новость без текста"
                        
                        # Добавляем информацию об авторе и времени
                        current_time = datetime.now().strftime('%H:%M:%S')
                        full_news = (
                            f"📰 <b>Новость в {current_time}</b>\n"
                            f"👤 <i>{message.author.name}</i>\n\n"
                            f"{news_text}"
                        )
                        
                        send_telegram(NEWS_TELEGRAM_CHANNEL, full_news)
                        logger.info("✅ Новость отправлена в Telegram")
                    
                    return  # Не обрабатываем как сток
                
                # ===== КАНАЛ СО СТОКАМИ =====
                if channel_id != STOCKS_CHANNEL_ID:
                    return
                
                # Проверяем автора (ищем Kiro или другого бота)
                if 'kiro' not in message.author.name.lower():
                    return
                
                # Защита от дублей
                if message.id in processed_messages:
                    logger.info(f"⏭️ Пропускаем дубль {message.id}")
                    return
                
                processed_messages.add(message.id)
                if len(processed_messages) > MAX_CACHE_SIZE:
                    processed_messages.remove(next(iter(processed_messages)))
                
                logger.info(f"📨 Сообщение от Kiro (ID: {message.id})")
                
                full_content = extract_full_content(message)
                if not full_content:
                    logger.info("📭 Сообщение пустое")
                    return
                
                logger.info(f"📋 Полный сток ({len(full_content)} символов)")
                
                # Ищем предметы
                found_items = []
                lower_content = full_content.lower()
                
                for item_name, item_config in TARGET_ITEMS.items():
                    for keyword in item_config['keywords']:
                        if keyword.lower() in lower_content:
                            found_items.append(item_name)
                            logger.info(f"🎯 Найдено: {keyword} → {item_config['display_name']}")
                            break
                
                current_time = datetime.now().strftime('%H:%M:%S')
                
                if found_items:
                    for item_name in found_items:
                        item_config = TARGET_ITEMS[item_name]
                        found_items_count[item_name] += 1
                        
                        # Стикер в канал
                        if item_config['sticker_id']:
                            send_telegram_sticker(STOCKS_TELEGRAM_CHANNEL, item_config['sticker_id'])
                        
                        logger.info(f"✅ {item_config['emoji']} {item_config['display_name']} в {current_time}")
                    
                    # Полный сток в бота
                    found_items_list = "\n".join([f"• {TARGET_ITEMS[name]['emoji']} {TARGET_ITEMS[name]['display_name']}" for name in found_items])
                    
                    formatted_stock = full_content
                    if len(formatted_stock) > 3000:
                        formatted_stock = formatted_stock[:3000] + "\n... (сообщение обрезано)"
                    
                    bot_message = (
                        f"🎯 <b>Обнаружены предметы в {current_time}:</b>\n"
                        f"{found_items_list}\n\n"
                        f"📋 <b>Полный сток:</b>\n"
                        f"<pre>{formatted_stock}</pre>\n\n"
                        f"#сток"
                    )
                    
                    send_to_bot(bot_message)
                    logger.info(f"📨 Полный сток отправлен в бота ({len(found_items)} предметов)")
                    
                else:
                    logger.info("📭 Целевые предметы не найдены")
                    
                    formatted_stock = full_content
                    if len(formatted_stock) > 3000:
                        formatted_stock = formatted_stock[:3000] + "\n... (сообщение обрезано)"
                    
                    bot_message = (
                        f"📊 <b>Сток от Kiro в {current_time}</b>\n"
                        f"🎯 Целевые предметы: не найдены\n\n"
                        f"📋 <b>Полный сток:</b>\n"
                        f"<pre>{formatted_stock}</pre>"
                    )
                    send_to_bot(bot_message)
                    logger.info("📨 Пустой сток отправлен в бота")
                    
            except Exception as e:
                logger.error(f"💥 Ошибка обработки сообщения: {e}")
                error_msg = f"⚠️ <b>Ошибка обработки сообщения:</b>\n<code>{str(e)[:200]}</code>"
                send_to_bot(error_msg)
        
        @client.event
        async def on_disconnect():
            global discord_connected
            discord_connected = False
            logger.warning("⚠️ Discord WebSocket отключен")
            send_to_bot("⚠️ <b>Discord WebSocket отключен</b>\nАвтопереподключение...")
        
        @client.event 
        async def on_resumed():
            global discord_connected
            discord_connected = True
            logger.info("✅ Discord WebSocket восстановлен")
            send_to_bot("✅ <b>Discord WebSocket восстановлен</b>")
        
        logger.info('🔗 Подключение к Discord...')
        client.run(DISCORD_TOKEN)
        
    except Exception as e:
        global discord_connected
        discord_connected = False
        logger.error(f"💥 Ошибка подключения к Discord: {e}")
        send_to_bot(f"🚨 <b>Discord не подключен:</b>\n<code>{str(e)[:200]}</code>\n\nFlask продолжает работу. Повторная попытка через 60 секунд...")
        
        # Бесконечный цикл с попытками переподключения
        while True:
            logger.info("⏳ Ожидание 60 секунд перед следующей попыткой подключения к Discord...")
            time.sleep(60)
            logger.info("🔄 Повторная попытка подключения к Discord...")
            
            try:
                # Рекурсивный вызов с теми же параметрами
                run_discord_bot()
                break  # Если подключились, выходим из цикла
            except Exception as retry_e:
                logger.error(f"❌ Очередная ошибка подключения: {retry_e}")
                continue

# ==================== ЗАПУСК ВСЕГО ====================
if __name__ == '__main__':
    print('=' * 60)
    print('🚀 ЗАПУСК МОНИТОРИНГА НОВОЙ ИГРЫ')
    print('=' * 60)
    print(f'📦 Канал стоков: {STOCKS_CHANNEL_ID}')
    if NEWS_CHANNEL_ID:
        print(f'📰 Канал новостей: {NEWS_CHANNEL_ID}')
    print('🎯 Отслеживаю 5 предметов:')
    print('   🍒 Cherry')
    print('   🥬 Cabbage')
    print('   💧 Super Sprinkler (только точное совпадение)')
    print('   🎋 Bamboo')
    print('   🥭 Mango')
    print('📨 В канал стоков: стикер')
    print('🤖 В бота: полный сток + уведомления')
    if NEWS_CHANNEL_ID:
        print('📰 Новости: пересылка в отдельный канал')
    print('🛡️ Защита от дублей: Да')
    print('🏓 Самопинг: каждые 8 минут')
    print('=' * 60)
    
    # Запускаем Flask
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    time.sleep(3)
    
    # Запускаем самопинг
    ping_thread = threading.Thread(target=self_pinger, daemon=True)
    ping_thread.start()
    
    # Запускаем Discord бота (в отдельном потоке, чтобы не блокировать)
    discord_thread = threading.Thread(target=run_discord_bot, daemon=True)
    discord_thread.start()
    
    # Бесконечное ожидание, чтобы главный поток не завершался
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("🛑 Остановка бота")
