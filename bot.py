#!/usr/bin/env python3
"""
🚀 МОНИТОРИНГ KIRO - РАБОЧАЯ ВЕРСИЯ
Простой и понятный код без сложной асинхронщины
"""

import os
import discord
import asyncio
from telegram import Bot
from flask import Flask
import threading
from datetime import datetime
import time

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

if not DISCORD_CHANNEL_IDS or DISCORD_CHANNEL_IDS == ['']:
    print('❌ Укажите DISCORD_CHANNEL_IDS через запятую')
    exit(1)

# ==================== ОТСЛЕЖИВАЕМЫЕ ПРЕДМЕТЫ ====================
TARGET_ITEMS = {
    'octobloom': {'keywords': ['octobloom', 'октоблум'], 'emoji': '🐙', 'display_name': 'Octobloom'},
    'zebrazinkle': {'keywords': ['zebrazinkle', 'zebra zinkle'], 'emoji': '🦓', 'display_name': 'Zebrazinkle'},
    'firework_fern': {'keywords': ['firework fern', 'fireworkfern'], 'emoji': '🎆', 'display_name': 'Firework Fern'},
    'tomato': {'keywords': ['tomato', 'томат', 'помидор'], 'emoji': '🍅', 'display_name': 'Tomato'}
}

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
found_items = {item: 0 for item in TARGET_ITEMS}
start_time = datetime.now()
telegram_bot = None
discord_client = None

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_to_telegram_sync(item_config):
    """Синхронная отправка в Telegram (проще)"""
    import requests
    
    try:
        current_time = datetime.now().strftime('%H:%M:%S')
        text_message = f"{item_config['emoji']} <b>{item_config['display_name']}</b> найден в {current_time}"
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": text_message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            print(f"✅ Telegram: {item_config['emoji']} {item_config['display_name']}")
            return True
        else:
            print(f"❌ Ошибка Telegram {response.status_code}")
            return False
            
    except Exception as e:
        print(f'❌ Ошибка Telegram: {e}')
        return False

# ==================== DISCORD КЛИЕНТ ====================
def run_discord_bot():
    """Запускает Discord бота в отдельном потоке"""
    global discord_client
    
    # Создаем нового клиента
    intents = discord.Intents.default()
    intents.message_content = True
    
    client = discord.Client(intents=intents)
    discord_client = client
    
    @client.event
    async def on_ready():
        print(f'✅ Discord бот {client.user} подключен!')
        print(f'👀 Каналы: {", ".join(DISCORD_CHANNEL_IDS)}')
        
        # Стартовое сообщение в Telegram
        items_list = "\n".join([f"{item['emoji']} {item['display_name']}" for item in TARGET_ITEMS.values()])
        send_to_telegram_sync({
            'emoji': '🚀',
            'display_name': f'Мониторинг Kiro запущен!\n\n📊 Отслеживаю:\n{items_list}'
        })
    
    @client.event
    async def on_message(message):
        # 1. Проверяем канал
        if str(message.channel.id) not in DISCORD_CHANNEL_IDS:
            return
        
        # 2. Проверяем автора
        if BOT_NAME_TO_TRACK and BOT_NAME_TO_TRACK not in message.author.name.lower():
            return
        
        print(f'📩 Сообщение от {message.author.name}: {message.content[:50]}...')
        
        # 3. Получаем текст
        full_text = message.content.lower()
        for embed in message.embeds:
            if embed.title: full_text += ' ' + embed.title.lower()
            if embed.description: full_text += ' ' + embed.description.lower()
        
        # 4. Ищем предметы
        for item_name, item_config in TARGET_ITEMS.items():
            for keyword in item_config['keywords']:
                if keyword.lower() in full_text:
                    # Используем синхронную функцию
                    send_to_telegram_sync(item_config)
                    found_items[item_name] += 1
                    break
    
    # Запускаем бота
    print('🔗 Подключение к Discord...')
    client.run(DISCORD_TOKEN)

# ==================== FLASK СЕРВЕР ====================
app = Flask(__name__)

@app.route('/')
def home():
    uptime = datetime.now() - start_time
    
    items_stats = []
    for item_name, count in found_items.items():
        if count > 0:
            item = TARGET_ITEMS[item_name]
            items_stats.append(f"{item['emoji']} {item['display_name']}: {count}")
    
    discord_status = "✅ Подключен" if discord_client and discord_client.is_ready() else "🔄 Подключение..."
    
    return f"""
    <html><body style="font-family: Arial; padding: 20px;">
        <h1>🌱 Мониторинг Kiro 🍅</h1>
        <p><strong>Discord:</strong> {discord_status}</p>
        <p><strong>Время работы:</strong> {str(uptime).split('.')[0]}</p>
        <p><strong>Каналов:</strong> {len(DISCORD_CHANNEL_IDS)}</p>
        <p><strong>Слежу за:</strong> {BOT_NAME_TO_TRACK}</p>
        
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
    discord_ok = discord_client and discord_client.is_ready()
    return {
        'status': 'healthy' if discord_ok else 'connecting',
        'timestamp': datetime.now().isoformat(),
        'discord_connected': discord_ok,
        'items_found': found_items
    }

@app.route('/test')
def test():
    """Тестовая отправка в Telegram"""
    result = send_to_telegram_sync({'emoji': '🧪', 'display_name': 'Тестовое сообщение от бота'})
    return {'test': 'sent', 'success': result}

# ==================== ЗАПУСК ====================
def run_flask():
    """Запускает Flask сервер"""
    try:
        from waitress import serve
        port = int(os.getenv('PORT', 10000))
        print(f'🌐 Веб-сервер на порту {port}')
        serve(app, host='0.0.0.0', port=port)
    except ImportError:
        print('⚠️ Waitress не установлен, запускаю dev-сервер')
        app.run(host='0.0.0.0', port=10000, debug=False)

if __name__ == '__main__':
    print('=' * 60)
    print('🚀 ЗАПУСК МОНИТОРИНГА KIRO')
    print('=' * 60)
    print(f'📊 Предметов: {len(TARGET_ITEMS)}')
    print(f'📺 Каналов: {len(DISCORD_CHANNEL_IDS)}')
    print(f'🤖 Отслеживаю: {BOT_NAME_TO_TRACK}')
    print('=' * 60)
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Даем Flask время запуститься
    time.sleep(2)
    
    # Запускаем Discord бота (блокирующий вызов)
    run_discord_bot()
