#!/usr/bin/env python3
"""
🚀 ПРОСТОЙ МОНИТОРИНГ KIRO ДЛЯ PYTHON 3.10
"""

import os
import discord
import requests
from flask import Flask
import threading
import time
from datetime import datetime

# ==================== НАСТРОЙКИ ====================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
DISCORD_CHANNEL_IDS = os.getenv('DISCORD_CHANNEL_IDS', '').split(',')
BOT_NAME_TO_TRACK = os.getenv('BOT_NAME_TO_TRACK', 'kiro')

# Проверка
if not DISCORD_TOKEN:
    print('❌ Нет DISCORD_TOKEN!')
    exit(1)
if not TELEGRAM_TOKEN:
    print('❌ Нет TELEGRAM_TOKEN!')
    exit(1)
if not TELEGRAM_CHANNEL_ID:
    print('❌ Нет TELEGRAM_CHANNEL_ID!')
    exit(1)

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram(text):
    """Отправляет сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f'❌ Ошибка Telegram: {e}')
        return False

# ==================== DISCORD БОТ ====================
class DiscordBot:
    def __init__(self):
        self.found_items = {
            'octobloom': 0,
            'zebrazinkle': 0,
            'firework_fern': 0,
            'tomato': 0
        }
        
    def run(self):
        """Запускает Discord бота"""
        intents = discord.Intents.default()
        intents.message_content = True
        
        client = discord.Client(intents=intents)
        
        @client.event
        async def on_ready():
            print(f'✅ Discord бот {client.user} подключен!')
            
            # Стартовое сообщение
            send_telegram(
                "✅ <b>Мониторинг Kiro запущен!</b>\n\n"
                "🎯 <b>Отслеживаю:</b>\n"
                "• 🐙 Octobloom\n"
                "• 🦓 Zebrazinkle\n"
                "• 🎆 Firework Fern\n"
                "• 🍅 Tomato\n\n"
                "🤖 Бот готов к работе!"
            )
        
        @client.event
        async def on_message(message):
            # Проверяем канал
            if str(message.channel.id) not in DISCORD_CHANNEL_IDS:
                return
            
            # Проверяем автора
            if BOT_NAME_TO_TRACK.lower() not in message.author.name.lower():
                return
            
            # Ищем ключевые слова
            text = message.content.lower()
            
            items_found = []
            if 'octobloom' in text or 'октоблум' in text:
                items_found.append('🐙 Octobloom')
                self.found_items['octobloom'] += 1
            if 'zebrazinkle' in text:
                items_found.append('🦓 Zebrazinkle')
                self.found_items['zebrazinkle'] += 1
            if 'firework' in text:
                items_found.append('🎆 Firework Fern')
                self.found_items['firework_fern'] += 1
            if 'tomato' in text or 'томат' in text:
                items_found.append('🍅 Tomato')
                self.found_items['tomato'] += 1
            
            # Отправляем уведомления
            for item in items_found:
                current_time = datetime.now().strftime('%H:%M:%S')
                send_telegram(f"{item} найден в {current_time}")
                print(f"✅ Найден: {item}")
        
        # Запускаем
        print('🔗 Подключение к Discord...')
        client.run(DISCORD_TOKEN)

# ==================== FLASK СЕРВЕР ====================
app = Flask(__name__)
bot = DiscordBot()
start_time = datetime.now()

@app.route('/')
def home():
    uptime = datetime.now() - start_time
    
    stats = []
    for name, count in bot.found_items.items():
        if count > 0:
            emoji = '🐙' if name == 'octobloom' else '🦓' if name == 'zebrazinkle' else '🎆' if name == 'firework_fern' else '🍅'
            stats.append(f"{emoji} {name}: {count}")
    
    return f"""
    <html><body style="font-family: Arial; padding: 20px;">
        <h1>🌱 Мониторинг Kiro 🍅</h1>
        <p><strong>Статус:</strong> ✅ Работает</p>
        <p><strong>Время работы:</strong> {str(uptime).split('.')[0]}</p>
        <p><strong>Каналов:</strong> {len(DISCORD_CHANNEL_IDS)}</p>
        
        <h2>📊 Найдено:</h2>
        <ul>{''.join([f'<li>{stat}</li>' for stat in stats]) if stats else '<li>Пока ничего</li>'}</ul>
        
        <p><em>⏰ {datetime.now().strftime('%H:%M:%S')}</em></p>
    </body></html>
    """

@app.route('/health')
def health():
    return {'status': 'healthy', 'time': datetime.now().isoformat()}

# ==================== ЗАПУСК ====================
def run_flask():
    """Запускает Flask сервер"""
    from waitress import serve
    port = int(os.getenv('PORT', 10000))
    print(f'🌐 Веб-сервер на порту {port}')
    serve(app, host='0.0.0.0', port=port)

if __name__ == '__main__':
    print('=' * 60)
    print('🚀 ЗАПУСК МОНИТОРИНГА KIRO')
    print('=' * 60)
    
    # Запускаем Flask в фоне
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Даем Flask время запуститься
    time.sleep(3)
    
    # Запускаем Discord бота (блокирующий вызов)
    try:
        bot.run()
    except Exception as e:
        print(f'❌ Ошибка Discord: {e}')
        print('🔄 Перезапуск через 30 секунд...')
        time.sleep(30)
