#!/usr/bin/env python3
"""
🚀 ПРОСТОЙ МОНИТОРИНГ KIRO ДЛЯ DISCORD → TELEGRAM
Без WebSocket, без API запросов - только Discord Gateway
"""

import os
import discord
from telegram import Bot
from telegram.error import TelegramError
from flask import Flask
import threading
import waitress
from datetime import datetime

# ==================== НАСТРОЙКИ ====================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_IDS = os.getenv('DISCORD_CHANNEL_IDS', '').split(',')
BOT_NAME_TO_TRACK = os.getenv('BOT_NAME_TO_TRACK', 'kiro').lower()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Проверка переменных
if not DISCORD_TOKEN:
    print('❌ ОШИБКА: Нет DISCORD_TOKEN!')
    exit(1)
if not TELEGRAM_TOKEN:
    print('❌ ОШИБКА: Нет TELEGRAM_TOKEN!')
    exit(1)
if not TELEGRAM_CHANNEL_ID:
    print('❌ ОШИБКА: Нет TELEGRAM_CHANNEL_ID!')
    exit(1)
if not DISCORD_CHANNEL_IDS or DISCORD_CHANNEL_IDS == ['']:
    print('❌ ОШИБКА: Нет DISCORD_CHANNEL_IDS!')
    exit(1)

# ==================== ОТСЛЕЖИВАЕМЫЕ ПРЕДМЕТЫ ====================
TARGET_ITEMS = {
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
    'tomato': {
        'keywords': ['tomato', 'томат', 'помидор', ':tomato:'],
        'sticker_id': "CAACAgIAAxkBAAIBZWgAAW2x6Ff3AAH00kG0HXKd9FJwfgACtgwAAuCTQUsAAVKDEv2u__U0BA",
        'emoji': '🍅',
        'display_name': 'Tomato'
    }
}

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
print('=' * 60)
print('🚀 ЗАПУСК МОНИТОРИНГА KIRO (чистая версия)')
print('=' * 60)

intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)
telegram_bot = Bot(token=TELEGRAM_TOKEN)
app = Flask(__name__)
found_items = {item: 0 for item in TARGET_ITEMS}
start_time = datetime.now()

# ==================== DISCORD ОБРАБОТКА ====================
@discord_client.event
async def on_ready():
    print(f'✅ Discord бот {discord_client.user} готов!')
    print(f'👀 Каналы: {", ".join(DISCORD_CHANNEL_IDS)}')
    print(f'🎯 Предметы: {", ".join([i["display_name"] for i in TARGET_ITEMS.values()])}')
    print('=' * 60)
    
    # Стартовое сообщение в Telegram
    try:
        items_list = "\n".join([f"{item['emoji']} {item['display_name']}" for item in TARGET_ITEMS.values()])
        await telegram_bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=f"✅ <b>Мониторинг Kiro запущен!</b>\n\n📊 Отслеживаю:\n{items_list}\n\n🤖 Бот работает!",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f'⚠️ Не отправил стартовое сообщение: {e}')

@discord_client.event
async def on_message(message):
    # Проверяем канал
    if str(message.channel.id) not in DISCORD_CHANNEL_IDS:
        return
    
    # Проверяем автора (если нужно)
    if BOT_NAME_TO_TRACK and BOT_NAME_TO_TRACK not in message.author.name.lower():
        return
    
    # Получаем текст
    full_text = message.content.lower()
    for embed in message.embeds:
        if embed.title: full_text += ' ' + embed.title.lower()
        if embed.description: full_text += ' ' + embed.description.lower()
    
    # Ищем предметы
    for item_name, item_config in TARGET_ITEMS.items():
        for keyword in item_config['keywords']:
            if keyword.lower() in full_text:
                await send_to_telegram(item_config)
                found_items[item_name] += 1
                break

async def send_to_telegram(item_config):
    try:
        current_time = datetime.now().strftime('%H:%M:%S')
        text_message = f"{item_config['emoji']} <b>{item_config['display_name']}</b> найден в {current_time}"
        
        await telegram_bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=text_message,
            parse_mode='HTML'
        )
        
        if item_config.get('sticker_id'):
            await telegram_bot.send_sticker(
                chat_id=TELEGRAM_CHANNEL_ID,
                sticker=item_config['sticker_id'],
                disable_notification=True
            )
        
        print(f"✅ Telegram: {item_config['emoji']} {item_config['display_name']}")
        
    except Exception as e:
        print(f'❌ Ошибка Telegram: {e}')

# ==================== FLASK СЕРВЕР ====================
@app.route('/')
def home():
    uptime = datetime.now() - start_time
    items_stats = []
    for item_name, count in found_items.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            items_stats.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    return f"""
    <html><body style="font-family: Arial; padding: 20px;">
        <h1>🌱 Мониторинг Kiro 🍅</h1>
        <p><strong>Статус:</strong> ✅ Работает</p>
        <p><strong>Время работы:</strong> {str(uptime).split('.')[0]}</p>
        <p><strong>Каналов:</strong> {len(DISCORD_CHANNEL_IDS)}</p>
        
        <h2>🎯 Предметы:</h2>
        <ul><li>🐙 Octobloom</li><li>🦓 Zebrazinkle</li>
        <li>🎆 Firework Fern</li><li>🍅 Tomato</li></ul>
        
        <h2>📊 Найдено:</h2>
        <ul>{''.join([f'<li>{stat}</li>' for stat in items_stats]) if items_stats else '<li>Пока ничего</li>'}</ul>
        
        <p><em>⏰ {datetime.now().strftime('%H:%M:%S')}</em></p>
    </body></html>
    """

@app.route('/health')
def health():
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    def run_flask():
        port = int(os.getenv('PORT', 10000))
        print(f'🌐 Веб-сервер на порту {port}')
        waitress.serve(app, host='0.0.0.0', port=port)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print('🔗 Подключение к Discord...')
    discord_client.run(DISCORD_TOKEN)
