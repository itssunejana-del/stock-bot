#!/usr/bin/env python3
"""
🚀 МОНИТОРИНГ KIRO (WebSocket + Полные логи стоков)
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

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram(chat_id, text, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Telegram отправлено в {chat_id}: {text[:50]}...")
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
        'sticker_id': "CAACAgIAAxkBAAEP1btpIXhIEvgVEK4c6ugJv1EgP7UY-wAChokAAtZpCElVMcRUgb_jdDYE",
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
        </style>
    </head>
    <body>
        <h1>🌱 Мониторинг Kiro 🍅</h1>
        
        <div class="card">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> <span class="status-ok">✅ WebSocket активен</span></p>
            <p><strong>Время работы:</strong> {uptime_str}</p>
            <p><strong>Самопингов:</strong> {ping_count}</p>
            <p><strong>Последний пинг:</strong> {last_ping_time.strftime('%H:%M:%S') if last_ping_time else 'Еще не было'}</p>
            <p><strong>Последнее обновление:</strong> {datetime.now().strftime('%H:%M:%S')}</p>
        </div>
        
        <div class="card">
            <h2>🎯 Отслеживаемые предметы</h2>
            <ul>
                <li>🐙 Octobloom</li>
                <li>🦓 Zebrazinkle</li>
                <li>🎆 Firework Fern</li>
                <li>🍅 Tomato (для теста)</li>
            </ul>
            <p><em>📨 В канал: стикер при находке<br>🤖 В бота: полный сток + уведомление</em></p>
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
            <p><strong>Автопереподключение:</strong> Да</p>
            <p><strong>Уведомления:</strong> Стикеры в канал + логи в бота</p>
        </div>
        
        <div class="card">
            <h2>🔍 Для тестирования</h2>
            <p><strong>Напиши в Discord канал:</strong> <code>tomato</code> или <code>🍅</code></p>
            <p><strong>Бот отправит:</strong> Стикер в канал + полный сток в бота</p>
            <p><a href="/health">Статус здоровья</a> | <a href="/test">Тест работы</a></p>
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
        'python_version': '3.10.13',
        'service_url': RENDER_SERVICE_URL,
        'last_update': datetime.now().strftime('%H:%M:%S')
    }

@app.route('/test')
def test():
    """Тестовая страница"""
    send_to_bot("🧪 <b>Тест от бота!</b>\nЕсли видишь это - бот работает!")
    send_to_channel("🧪 <b>Тест в канал!</b>\nБот активен и мониторит стоки.")
    return "✅ Тестовые сообщения отправлены в Telegram"

# ==================== ЗАПУСК FLASK В ФОНЕ ====================
def run_flask():
    """Запускает Flask сервер в фоновом режиме"""
    from waitress import serve
    port = int(os.getenv('PORT', 10000))
    logger.info(f'🌐 Веб-сервер запущен на порту {port}')
    serve(app, host='0.0.0.0', port=port)

# ==================== ЗАПУСК ВСЕГО ====================
if __name__ == '__main__':
    print('=' * 60)
    print('🚀 ЗАПУСК МОНИТОРИНГА KIRO')
    print('=' * 60)
    print(f'🌱 Канал Discord: {SEEDS_CHANNEL_ID}')
    print(f'📢 Канал Telegram: {TELEGRAM_CHANNEL_ID}')
    print(f'🤖 Бот Telegram: {TELEGRAM_BOT_CHAT_ID}')
    print('🎯 Отслеживаю: 4 предмета (включая томат)')
    print('📨 В канал: стикеры при находке')
    print('🤖 В бота: полные логи стоков')
    print('🏓 Самопинг: каждые 8 минут')
    print('=' * 60)
    
    # Запускаем Flask в отдельном потоке (как демон)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Даем Flask время запуститься
    time.sleep(3)
    
    # Запускаем самопинг в отдельном потоке
    ping_thread = threading.Thread(target=self_pinger, daemon=True)
    ping_thread.start()
    
    # ==================== DISCORD БОТ В ОСНОВНОМ ПОТОКЕ ====================
    try:
        # Инициализируем Discord бота
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        
        client = discord.Client(intents=intents)
        
        @client.event
        async def on_ready():
            logger.info(f'✅ Discord бот {client.user} подключен через WebSocket!')
            
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
                f"📨 <b>Логистика уведомлений:</b>\n"
                f"• В канал: 🎯 Стикер при находке\n"
                f"• В бота: 📋 Полный сток + уведомление\n"
                f"✅ Бот готов к работе!"
            )
        
        @client.event
        async def on_message(message):
            try:
                # Пропускаем сообщения от самого бота
                if message.author == client.user:
                    return
                
                # Проверяем канал
                if str(message.channel.id) != SEEDS_CHANNEL_ID:
                    return
                
                # Проверяем автора (ищем Kiro)
                if 'kiro' not in message.author.name.lower():
                    return
                
                logger.info(f"📨 Сообщение от Kiro получено")
                
                # Получаем ВСЁ содержимое сообщения
                full_content = ""
                
                # 1. Текст сообщения
                if message.content:
                    full_content += f"{message.content}\n\n"
                
                # 2. Эмбеды (основной контент стоков)
                if message.embeds:
                    for embed in message.embeds:
                        if embed.title:
                            full_content += f"**{embed.title}**\n"
                        if embed.description:
                            full_content += f"{embed.description}\n"
                        if embed.fields:
                            for field in embed.fields:
                                full_content += f"\n**{field.name}**\n{field.value}\n"
                        if embed.footer:
                            full_content += f"\n{embed.footer.text}\n"
                
                # Логируем полный контент
                logger.info(f"📋 Полный сток:\n{full_content[:500]}...")
                
                # Ищем целевые предметы
                found_items = []
                lower_content = full_content.lower()
                
                for item_name, item_config in TARGET_ITEMS.items():
                    for keyword in item_config['keywords']:
                        if keyword.lower() in lower_content:
                            found_items.append(item_name)
                            logger.info(f"🎯 Найдено: {keyword} → {item_config['display_name']}")
                            break
                
                # Если нашли целевые предметы - отправляем уведомления
                if found_items:
                    current_time = datetime.now().strftime('%H:%M:%S')
                    
                    # Обрабатываем каждый найденный предмет
                    for item_name in found_items:
                        item_config = TARGET_ITEMS[item_name]
                        found_items_count[item_name] += 1
                        
                        # 1. В КАНАЛ: стикер
                        if 'sticker_id' in item_config and item_config['sticker_id']:
                            sticker_sent = send_telegram_sticker(TELEGRAM_CHANNEL_ID, item_config['sticker_id'])
                            if sticker_sent:
                                logger.info(f"📢 Стикер {item_config['emoji']} отправлен в канал")
                        
                        # 2. В КАНАЛ: текстовое уведомление
                        channel_message = f"{item_config['emoji']} <b>{item_config['display_name']}</b> найден в {current_time}"
                        send_to_channel(channel_message)
                        logger.info(f"✅ {item_config['emoji']} {item_config['display_name']} в {current_time}")
                    
                    # 3. В БОТА: полный сток + список найденного
                    found_items_list = "\n".join([f"• {TARGET_ITEMS[name]['emoji']} {TARGET_ITEMS[name]['display_name']}" for name in found_items])
                    
                    bot_message = (
                        f"🎯 <b>Обнаружены предметы в {current_time}:</b>\n"
                        f"{found_items_list}\n\n"
                        f"📋 <b>Полный сток:</b>\n"
                        f"<pre>{full_content[:1500]}</pre>\n\n"
                        f"#сток #{current_time.replace(':', '')}"
                    )
                    
                    send_to_bot(bot_message)
                    logger.info(f"📨 Полный сток отправлен в бота ({len(found_items)} предметов)")
                    
                else:
                    # Если целевых предметов нет, но есть сообщение от Kiro
                    logger.info("📭 Целевые предметы не найдены в стоке")
                    
                    # Всё равно отправляем полный сток в бота для мониторинга
                    if full_content.strip():
                        bot_message = (
                            f"📊 <b>Сток от Kiro в {datetime.now().strftime('%H:%M:%S')}</b>\n"
                            f"🎯 Целевые предметы: не найдены\n\n"
                            f"📋 <b>Полный сток:</b>\n"
                            f"<pre>{full_content[:1500]}</pre>"
                        )
                        send_to_bot(bot_message)
                        logger.info("📨 Пустой сток отправлен в бота для мониторинга")
                        
            except Exception as e:
                logger.error(f"💥 Ошибка обработки сообщения: {e}")
                error_msg = f"⚠️ <b>Ошибка обработки сообщения:</b>\n<code>{str(e)[:200]}</code>"
                send_to_bot(error_msg)
        
        @client.event
        async def on_disconnect():
            logger.warning("⚠️ Discord WebSocket отключен")
            send_to_bot("⚠️ <b>Discord WebSocket отключен</b>\nБот попробует переподключиться автоматически.")
        
        @client.event 
        async def on_resumed():
            logger.info("✅ Discord WebSocket восстановлен")
            send_to_bot("✅ <b>Discord WebSocket восстановлен</b>\nМониторинг продолжается.")
        
        @client.event
        async def on_error(event, *args, **kwargs):
            logger.error(f"⚠️ Discord ошибка в событии: {event}")
            if len(args) > 0:
                logger.error(f"Аргументы: {args[0]}")
        
        # Запускаем Discord бота (ОСНОВНОЙ ПОТОК - БЛОКИРУЮЩИЙ)
        logger.info('🔗 Подключение к Discord через WebSocket...')
        client.run(DISCORD_TOKEN)
        
    except KeyboardInterrupt:
        logger.info("🛑 Остановка бота по команде пользователя")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка запуска Discord: {e}")
        send_to_bot(f"🚨 <b>Критическая ошибка Discord:</b>\n<code>{str(e)[:200]}</code>")
