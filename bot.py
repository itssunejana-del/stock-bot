from flask import Flask
import requests
import os
import time
import logging
import threading
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

def send_telegram(text):
    """Отправляет сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        response = requests.post(url, data=data, timeout=10)
        logger.info(f"📱 Telegram: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")
        return False

def check_discord_messages():
    """Проверяет сообщения и эмбады в канале Discord"""
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=10"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        logger.info("🔍 Проверяю последние 10 сообщений...")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            logger.info(f"📨 Найдено сообщений: {len(messages)}")
            
            # Проверяем каждое сообщение
            for i, message in enumerate(messages):
                message_id = message['id']
                author = message['author']['username']
                content = message.get('content', '')
                embeds = message.get('embeds', [])
                
                logger.info(f"📝 Сообщение {i+1} от {author}:")
                logger.info(f"   🆔 ID: {message_id}")
                logger.info(f"   📄 Текст: '{content[:50]}...'" if content else "   📄 Текст: ПУСТО")
                logger.info(f"   🎨 Эмбадов: {len(embeds)}")
                
                # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ЭМБАДОВ
                for j, embed in enumerate(embeds):
                    logger.info(f"   🔍 Эмбад {j+1}:")
                    
                    # Все возможные поля эмбада
                    title = embed.get('title', 'НЕТ ЗАГОЛОВКА')
                    description = embed.get('description', 'НЕТ ОПИСАНИЯ')
                    fields = embed.get('fields', [])
                    
                    logger.info(f"      📌 Заголовок: {title}")
                    logger.info(f"      📋 Описание: {description[:100]}...")
                    logger.info(f"      📊 Полей: {len(fields)}")
                    
                    # Проверяем все текстовые части эмбада на Tomato
                    all_embed_text = f"{title} {description}"
                    
                    # Добавляем текст из полей (fields)
                    for field in fields:
                        field_name = field.get('name', '')
                        field_value = field.get('value', '')
                        all_embed_text += f" {field_name} {field_value}"
                    
                    logger.info(f"      🔎 Весь текст эмбада: {all_embed_text[:150]}...")
                    
                    # Ищем Tomato в любом виде
                    if any(tomato_keyword in all_embed_text for tomato_keyword in ['Tomato', ':Tomato:', '🍅']):
                        logger.info("🎯 TOMATO НАЙДЕН В ЭМБАДЕ!")
                        
                        # Формируем красивое сообщение для Telegram
                        telegram_message = f"🚨 TOMATO В ПРОДАЖЕ! 🍅\n\n"
                        
                        if title and title != 'НЕТ ЗАГОЛОВКА':
                            telegram_message += f"📌 {title}\n"
                        
                        if description and description != 'НЕТ ОПИСАНИЯ':
                            telegram_message += f"📋 {description}\n"
                        
                        # Добавляем поля если есть
                        for field in fields:
                            field_name = field.get('name', '')
                            field_value = field.get('value', '')
                            if field_name and field_value:
                                telegram_message += f"• {field_name}: {field_value}\n"
                        
                        return True, telegram_message
                
                # Также проверяем обычный текст сообщения
                if any(tomato_keyword in content for tomato_keyword in ['Tomato', ':Tomato:', '🍅']):
                    logger.info("🎯 TOMATO НАЙДЕН В ТЕКСТЕ!")
                    return True, f"🚨 TOMATO В ПРОДАЖЕ! 🍅\n\n{content}"
            
            return False, "Tomato не найден в последних сообщениях"
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            return False, f"Ошибка API: {response.status_code}"
            
    except Exception as e:
        logger.error(f"💥 Ошибка при проверке сообщений: {e}")
        return False, f"Ошибка: {str(e)}"

@app.route('/')
def home():
    return """
    <h1>🍅 Tomato Monitor Bot</h1>
    <p>Бот работает и мониторит канал Discord!</p>
    <p><a href="/check">🔍 Проверить сообщения (ДЕТАЛЬНЫЙ АНАЛИЗ)</a></p>
    <p><a href="/test">🧪 Тест уведомления</a></p>
    """

@app.route('/check')
def check_messages():
    """Проверяет сообщения с детальным анализом"""
    logger.info("🔍 ЗАПУСК ДЕТАЛЬНОЙ ПРОВЕРКИ СООБЩЕНИЙ")
    found, message = check_discord_messages()
    
    result = "🍅 TOMATO НАЙДЕН!" if found else "❌ Tomato не найден"
    
    return f"""
    <h1>Результат проверки</h1>
    <p>Результат: <b>{result}</b></p>
    <p>Сообщение: {message}</p>
    <p><small>Проверьте логи в Render для детальной информации</small></p>
    <p><a href="/">← Назад</a></p>
    """

@app.route('/test')
def test_notification():
    """Тестовая страница - отправляет fake уведомление"""
    test_message = """Vulcan • Grow a Garden Stocks
SEEDS STOCK
:Tomato: Tomato x5
:Carrot: Carrot x10
:Strawberry: Strawberry x3"""
    
    send_telegram("🧪 ТЕСТ: TOMATO В ПРОДАЖЕ! 🍅")
    send_telegram(f"📋 {test_message}")
    
    return """
    <h1>🧪 Тестовое уведомление отправлено!</h1>
    <p>Проверьте Telegram - должно прийти тестовое сообщение о Tomato</p>
    <p><a href="/">← Назад</a></p>
    """

def discord_monitor():
    """Основной мониторинг"""
    logger.info("🔄 ЗАПУСК ОСНОВНОГО МОНИТОРИНГА")
    
    last_detected = False
    
    while True:
        try:
            found, message = check_discord_messages()
            
            if found and not last_detected:
                logger.info("🎯 TOMATO ОБНАРУЖЕН - ОТПРАВЛЯЮ УВЕДОМЛЕНИЕ!")
                send_telegram(message)
                last_detected = True
            elif not found:
                last_detected = False
                
            time.sleep(30)  # Проверяем каждые 30 секунд
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            time.sleep(60)

# Запускаем приложение
if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК СИСТЕМЫ")
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=discord_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # Отправляем уведомление о запуске
    send_telegram("🔍 Бот перезапущен! Начинаю мониторинг Tomato...")
    
    app.run(host='0.0.0.0', port=5000)
