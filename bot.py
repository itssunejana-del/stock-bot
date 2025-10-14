from flask import Flask
import requests
import os
import threading
import time

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(message):
    print(f"Отправляю в Telegram: {message}")
    # Пока только тестируем

def bot_worker():
    print("🎃 Бот-воркер запущен!")
    send_telegram("🤖 Бот запущен на Render и работает 24/7!")
    
    while True:
        print("🔄 Бот проверяет сообщения...")
        time.sleep(60)  # Проверяем каждую минуту

@app.route('/')
def home():
    return "🎃 Pumpkin Bot работает! Проверяю Discord..."

# Запускаем бота в отдельном потоке
bot_thread = threading.Thread(target=bot_worker)
bot_thread.daemon = True
bot_thread.start()

if __name__ == '__main__':
    print("✅ Веб-сервер и бот запущены!")
    app.run(host='0.0.0.0', port=5000)
