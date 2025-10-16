from flask import Flask
import requests
import os
import time
import logging
import threading
import discord
from discord.ext import tasks

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Discord клиент
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
        logger.info("✅ Уведомление отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")

@client.event
async def on_ready():
    logger.info(f'✅ Discord бот вошел как {client.user}')
    send_telegram("🔍 Discord бот подключен! Мониторю сообщения...")

@client.event
async def on_message(message):
    # Игнорируем сообщения от самого себя
    if message.author == client.user:
        return
    
    # Проверяем что сообщение от Vulcan bot и содержит Tomato
    if 'Vulcan' in str(message.author) and 'Tomato' in message.content:
        logger.info("🍅 TOMATO ОБНАРУЖЕН!")
        send_telegram("🍅 TOMATO В ПРОДАЖЕ! 🍅")
        send_telegram(f"📋 {message.content}")

def start_discord_bot():
    """Запускает Discord бота в отдельном потоке"""
    client.run(DISCORD_TOKEN)

@app.route('/')
def home():
    return "🍅 Мониторю сообщения Vulcan bot на предмет Tomato"

# Запускаем Discord бота
logger.info("🚀 Запускаю Discord монитор...")
discord_thread = threading.Thread(target=start_discord_bot)
discord_thread.daemon = True
discord_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
