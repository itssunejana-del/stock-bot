from flask import Flask
import requests
import os
import threading
import time
import logging
import discord

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)

# === НАСТРОЙКИ ===
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SHOP_BOT_ID = 1392612367329923175  # ID бота магазина

# Discord клиент с intents
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    logger.info(f'✅ Discord бот вошел как {client.user}')
    send_telegram("🤖 Discord бот подключен! Ожидаю Great Pumpkin...")

@client.event
async def on_message(message):
    # Игнорируем свои сообщения
    if message.author == client.user:
        return
    
    # Если сообщение от бота магазина
    if message.author.id == SHOP_BOT_ID:
        logger.info(f"📨 Сообщение от бота магазина: {message.content}")
        
        # Проверяем на наличие Great Pumpkin
        message_lower = message.content.lower()
        if any(word in message_lower for word in ['great pumpkin', 'greatpumpkin']):
            logger.info("🎃 ОБНАРУЖЕН GREAT PUMPKIN! Отправляю в Telegram...")
            send_telegram("🎃 🎃 🎃 GREAT PUMPKIN НАЙДЕН! 🎃 🎃 🎃")
            send_telegram(f"📋 Сообщение: {message.content}")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        response = requests.post(url, data=data)
        logger.info("✅ Сообщение отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")

def discord_bot_worker():
    logger.info("🎃 Запускаю Discord бота...")
    client.run(DISCORD_TOKEN)

@app.route('/')
def home():
    return "🎃 Pumpkin Bot работает! Мониторю Discord на предмет Great Pumpkin..."

# Запускаем Discord бота в отдельном потоке
logger.info("✅ Запускаю бота...")
discord_thread = threading.Thread(target=discord_bot_worker)
discord_thread.daemon = True
discord_thread.start()

if __name__ == '__main__':
    logger.info("🚀 Запускаю веб-сервер...")
    app.run(host='0.0.0.0', port=5000)
