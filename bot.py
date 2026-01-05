#!/usr/bin/env python3
"""
🚀 ПРОСТОЙ МОНИТОРИНГ KIRO ДЛЯ DISCORD → TELEGRAM
Автоматически следит за сообщениями Kiro и присылает уведомления в Telegram
"""

import os
import discord
import asyncio
from telegram import Bot
from telegram.error import TelegramError
from flask import Flask

# ==================== НАСТРОЙКИ ====================
# ВСЕ эти переменные должны быть в настройках Render (Environment Variables)

# Discord настройки
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_IDS = os.getenv('DISCORD_CHANNEL_IDS', '').split(',')
BOT_NAME_TO_TRACK = os.getenv('BOT_NAME_TO_TRACK', 'kiro').lower()

# Telegram настройки
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Проверяем, что все нужные переменные есть
if not DISCORD_TOKEN:
    print('❌ ОШИБКА: Нет DISCORD_TOKEN! Добавьте в настройки Render')
    exit(1)
if not TELEGRAM_TOKEN:
    print('❌ ОШИБКА: Нет TELEGRAM_TOKEN! Добавьте в настройки Render')
    exit(1)
if not TELEGRAM_CHANNEL_ID:
    print('❌ ОШИБКА: Нет TELEGRAM_CHANNEL_ID! Добавьте в настройки Render')
    exit(1)
if not DISCORD_CHANNEL_IDS or DISCORD_CHANNEL_IDS == ['']:
    print('❌ ОШИБКА: Нет DISCORD_CHANNEL_IDS! Добавьте ID каналов через запятую')
    exit(1)

# ==================== ОТСЛЕЖИВАЕМЫЕ ПРЕДМЕТЫ ====================
# Добавил томаты (tomato) как вы просили!
TARGET_ITEMS = {
    # 🌱 Семена (3 предмета)
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
    'firework_fern': {
        'keywords': ['firework fern', 'fireworkfern', ':fireworkfern', ':firework_fern:'],
        'sticker_id': "CAACAgIAAxkBAAEQHChpUBeOda8Uf0Uwig6BwvkW_z1ndAAC5Y0AAl8dgEoandjqAtpRWTYE",
        'emoji': '🎆',
        'display_name': 'Firework Fern'
    },
    
    # 🍅 ТОМАТЫ (добавлены по вашему запросу)
    'tomato': {
        'keywords': ['tomato', 'томат', 'помидор', ':tomato:'],
        'sticker_id': "CAACAgIAAxkBAAIBZWgAAW2x6Ff3AAH00kG0HXKd9FJwfgACtgwAAuCTQUsAAVKDEv2u__U0BA",  # Замените на реальный ID стикера
        'emoji': '🍅',
        'display_name': 'Tomato'
    }
}

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
print('=' * 60)
print('🚀 ЗАПУСК МОНИТОРИНГА KIRO С TOMATO')
print('=' * 60)

# Создаем Discord-бота с нужными разрешениями
intents = discord.Intents.default()
intents.message_content = True  # Это ОБЯЗАТЕЛЬНО для чтения сообщений

discord_client = discord.Client(intents=intents)

# Создаем Telegram-бота
telegram_bot = Bot(token=TELEGRAM_TOKEN)

# Создаем Flask-сервер для самопинга (чтобы Render не усыплял бота)
app = Flask(__name__)

# Счетчики для статистики
found_items = {}
for item in TARGET_ITEMS:
    found_items[item] = 0

# ==================== ОСНОВНАЯ ЛОГИКА ====================
@discord_client.event
async def on_ready():
    """Вызывается когда Discord-бот подключился"""
    print(f'✅ Discord бот {discord_client.user} готов к работе!')
    print(f'👀 Отслеживаю каналы: {", ".join(DISCORD_CHANNEL_IDS)}')
    print(f'🎯 Ищу предметы: {", ".join([item["display_name"] for item in TARGET_ITEMS.values()])}')
    print(f'🤖 Слежу за ботом: {BOT_NAME_TO_TRACK}')
    print('=' * 60)
    
    # Отправляем сообщение в Telegram о старте
    try:
        items_list = "\n".join([f"{item['emoji']} {item['display_name']}" for item in TARGET_ITEMS.values()])
        await telegram_bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=f"✅ <b>Мониторинг Kiro запущен!</b>\n\n📊 Отслеживаю:\n{items_list}\n\n🤖 Бот готов к работе!",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f'⚠️ Не удалось отправить стартовое сообщение в Telegram: {e}')

@discord_client.event
async def on_message(message):
    """Вызывается при каждом новом сообщении в Discord"""
    try:
        # 1. Проверяем, что сообщение в нужном канале
        if str(message.channel.id) not in DISCORD_CHANNEL_IDS:
            return
        
        # 2. Проверяем автора сообщения (только Kiro)
        author_name = message.author.name.lower()
        is_bot = message.author.bot
        
        # Если нужно следить только за конкретным ботом
        if BOT_NAME_TO_TRACK and BOT_NAME_TO_TRACK not in author_name:
            return
        
        # 3. Получаем весь текст сообщения
        full_text = message.content.lower()
        
        # Добавляем текст из эмбедов (если есть)
        for embed in message.embeds:
            if embed.title:
                full_text += ' ' + embed.title.lower()
            if embed.description:
                full_text += ' ' + embed.description.lower()
            # Поля эмбедов
            for field in embed.fields:
                if field.name:
                    full_text += ' ' + field.name.lower()
                if field.value:
                    full_text += ' ' + field.value.lower()
        
        # 4. Проверяем на ключевые слова
        found_in_this_message = []
        
        for item_name, item_config in TARGET_ITEMS.items():
            for keyword in item_config['keywords']:
                if keyword.lower() in full_text:
                    if item_name not in found_in_this_message:
                        found_in_this_message.append(item_name)
                        found_items[item_name] += 1
                    break  # Перестаем искать другие ключевые слова для этого предмета
        
        # 5. Если что-то нашли - отправляем в Telegram
        if found_in_this_message:
            for item_name in found_in_this_message:
                item_config = TARGET_ITEMS[item_name]
                await send_to_telegram(item_config)
                
    except Exception as e:
        print(f'❌ Ошибка при обработке сообщения: {e}')

async def send_to_telegram(item_config):
    """Отправляет уведомление в Telegram"""
    try:
        # Получаем текущее время
        from datetime import datetime
        current_time = datetime.now().strftime('%H:%M:%S')
        
        # Текстовое сообщение
        text_message = f"{item_config['emoji']} <b>{item_config['display_name']}</b> найден в {current_time}"
        
        # Отправляем текст
        await telegram_bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=text_message,
            parse_mode='HTML',
            disable_notification=False
        )
        
        # Отправляем стикер (если есть)
        if item_config.get('sticker_id'):
            await telegram_bot.send_sticker(
                chat_id=TELEGRAM_CHANNEL_ID,
                sticker=item_config['sticker_id'],
                disable_notification=True
            )
        
        print(f"✅ Отправлено в Telegram: {item_config['emoji']} {item_config['display_name']}")
        
    except TelegramError as e:
        print(f'❌ Ошибка Telegram: {e}')
    except Exception as e:
        print(f'❌ Неизвестная ошибка при отправке в Telegram: {e}')

# ==================== ВЕБ-СЕРВЕР ДЛЯ RENDER ====================
@app.route('/')
def home():
    """Главная страница для самопинга"""
    from datetime import datetime
    uptime = datetime.now() - start_time
    
    items_stats = []
    for item_name, count in found_items.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            items_stats.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    return f"""
    <html>
    <head><title>🌱 Мониторинг Kiro + Tomato 🍅</title></head>
    <body style="font-family: Arial; padding: 20px;">
        <h1>🌱 Мониторинг Kiro + Tomato 🍅</h1>
        <p><strong>Статус:</strong> ✅ Работает</p>
        <p><strong>Время работы:</strong> {str(uptime).split('.')[0]}</p>
        <p><strong>Отслеживаю каналы:</strong> {len(DISCORD_CHANNEL_IDS)} шт</p>
        
        <h2>🎯 Отслеживаемые предметы:</h2>
        <ul>
            <li>🐙 Octobloom</li>
            <li>🦓 Zebrazinkle</li>
            <li>🎆 Firework Fern</li>
            <li>🍅 Tomato (добавлен!)</li>
        </ul>
        
        <h2>📊 Найдено предметов:</h2>
        <ul>
            {''.join([f'<li>{stat}</li>' for stat in items_stats]) if items_stats else '<li>Пока ничего не найдено</li>'}
        </ul>
        
        <p><em>🤖 Бот автоматически отслеживает сообщения Kiro в Discord</em></p>
        <p><em>⏰ Последняя проверка: {datetime.now().strftime('%H:%M:%S')}</em></p>
    </body>
    </html>
    """

@app.route('/health')
def health():
    """Для проверки здоровья бота"""
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}

@app.route('/stats')
def stats():
    """Статистика бота"""
    return {
        'status': 'running',
        'items_found': found_items,
        'channels_monitored': DISCORD_CHANNEL_IDS,
        'bot_tracking': BOT_NAME_TO_TRACK
    }

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    import threading
    from datetime import datetime
    import waitress
    
    start_time = datetime.now()
    
    # Запускаем Flask-сервер в отдельном потоке
    def run_flask():
        port = int(os.getenv('PORT', 10000))
        print(f'🌐 Веб-сервер запущен на порту {port}')
        waitress.serve(app, host='0.0.0.0', port=port)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем Discord-бота
    print('🔗 Подключаюсь к Discord...')
    discord_client.run(DISCORD_TOKEN)
