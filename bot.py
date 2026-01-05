#!/usr/bin/env python3
"""
🚀 МОНИТОРИНГ KIRO ЧЕРЕЗ DISCORD GATEWAY
Нет запросов к API - только слушаем события
"""

import os
import discord
from telegram import Bot
from flask import Flask
import threading
from datetime import datetime

# ==================== НАСТРОЙКИ ====================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_IDS = os.getenv('DISCORD_CHANNEL_IDS', '').split(',')
BOT_NAME_TO_TRACK = os.getenv('BOT_NAME_TO_TRACK', 'kiro').lower()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Проверяем переменные
if not all([DISCORD_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID]):
    print('❌ Проверьте переменные в Render!')
    exit(1)

# ==================== ОТСЛЕЖИВАЕМЫЕ ПРЕДМЕТЫ ====================
TARGET_ITEMS = {
    'octobloom': {'keywords': ['octobloom', 'октоблум'], 'emoji': '🐙', 'display_name': 'Octobloom'},
    'zebrazinkle': {'keywords': ['zebrazinkle', 'zebra zinkle'], 'emoji': '🦓', 'display_name': 'Zebrazinkle'},
    'firework_fern': {'keywords': ['firework fern', 'fireworkfern'], 'emoji': '🎆', 'display_name': 'Firework Fern'},
    'tomato': {'keywords': ['tomato', 'томат', 'помидор'], 'emoji': '🍅', 'display_name': 'Tomato'}
}

# ==================== DISCORD CLIENT ====================
# Ключевое отличие: используем Gateway, а не API запросы
intents = discord.Intents.default()
intents.message_content = True  # Должен быть включен в Discord Dev Portal

client = discord.Client(intents=intents)
telegram_bot = Bot(token=TELEGRAM_TOKEN)
start_time = datetime.now()
found_items = {item: 0 for item in TARGET_ITEMS}

@client.event
async def on_ready():
    """Вызывается при подключении к Discord"""
    print(f'✅ Discord бот {client.user} готов!')
    print(f'👀 Слушаю каналы: {", ".join(DISCORD_CHANNEL_IDS)}')
    
    # Отправляем стартовое сообщение в Telegram
    try:
        items_list = "\n".join([f"{item['emoji']} {item['display_name']}" for item in TARGET_ITEMS.values()])
        await telegram_bot.send_message(
            TELEGRAM_CHANNEL_ID,
            f"✅ <b>Мониторинг Kiro запущен через Gateway!</b>\n\n📊 Отслеживаю:\n{items_list}\n\n🤖 Бот работает!",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f'⚠️ Не отправил стартовое сообщение: {e}')

@client.event
async def on_message(message):
    """Вызывается при КАЖДОМ новом сообщении в Discord"""
    # 1. Проверяем канал
    if str(message.channel.id) not in DISCORD_CHANNEL_IDS:
        return
    
    # 2. Проверяем автора (только Kiro)
    if BOT_NAME_TO_TRACK and BOT_NAME_TO_TRACK not in message.author.name.lower():
        return
    
    print(f'📩 Новое сообщение от {message.author.name} в #{message.channel.name}')
    
    # 3. Получаем текст
    full_text = message.content.lower()
    for embed in message.embeds:
        if embed.title: full_text += ' ' + embed.title.lower()
        if embed.description: full_text += ' ' + embed.description.lower()
    
    # 4. Ищем предметы
    for item_name, item_config in TARGET_ITEMS.items():
        for keyword in item_config['keywords']:
            if keyword.lower() in full_text:
                await send_to_telegram(item_config)
                found_items[item_name] += 1
                break

async def send_to_telegram(item_config):
    """Отправляет уведомление в Telegram"""
    try:
        current_time = datetime.now().strftime('%H:%M:%S')
        text_message = f"{item_config['emoji']} <b>{item_config['display_name']}</b> найден в {current_time}"
        
        await telegram_bot.send_message(
            TELEGRAM_CHANNEL_ID,
            text_message,
            parse_mode='HTML'
        )
        
        print(f"✅ Отправлено в Telegram: {item_config['emoji']} {item_config['display_name']}")
        
    except Exception as e:
        print(f'❌ Ошибка Telegram: {e}')

# ==================== FLASK СЕРВЕР ====================
app = Flask(__name__)

@app.route('/')
def home():
    """Главная страница"""
    uptime = datetime.now() - start_time
    
    items_stats = []
    for item_name, count in found_items.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            items_stats.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    return f"""
    <html><body style="font-family: Arial; padding: 20px;">
        <h1>🌱 Мониторинг Kiro (Gateway) 🍅</h1>
        <p><strong>Статус:</strong> ✅ Работает через WebSocket</p>
        <p><strong>Время работы:</strong> {str(uptime).split('.')[0]}</p>
        <p><strong>Каналов:</strong> {len(DISCORD_CHANNEL_IDS)}</p>
        
        <h2>🎯 Отслеживаю:</h2>
        <ul><li>🐙 Octobloom</li><li>🦓 Zebrazinkle</li>
        <li>🎆 Firework Fern</li><li>🍅 Tomato</li></ul>
        
        <h2>📊 Найдено:</h2>
        <ul>{''.join([f'<li>{stat}</li>' for stat in items_stats]) if items_stats else '<li>Пока ничего</li>'}</ul>
        
        <p><em>🤖 Discord отправляет сообщения сам, нет запросов к API</em></p>
    </body></html>
    """

@app.route('/health')
def health():
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}

# ==================== ЗАПУСК ====================
def run_flask():
    """Запускает Flask сервер"""
    from waitress import serve
    port = int(os.getenv('PORT', 10000))
    print(f'🌐 Веб-сервер запущен на порту {port}')
    serve(app, host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем Discord клиент (WebSocket соединение)
    print('=' * 60)
    print('🚀 ЗАПУСК МОНИТОРИНГА ЧЕРЕЗ DISCORD GATEWAY')
    print('=' * 60)
    print('✅ НЕТ запросов к Discord API')
    print('✅ Discord сам присылает сообщения через WebSocket')
    print('✅ Нет блокировок за лимиты')
    print('=' * 60)
    
    client.run(DISCORD_TOKEN)
