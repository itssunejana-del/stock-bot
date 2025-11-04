from flask import Flask
import requests
import os
import time
import logging
import threading
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

# Глобальные переменные
last_processed_id = None
startup_time = datetime.now()

def send_telegram(text):
    """Отправляет сообщение в Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ Не настроены переменные Telegram")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID, 
            "text": text,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено в Telegram: {text}")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def get_discord_messages():
    """Получает сообщения из Discord канала"""
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=10"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"❌ Ошибка Discord API: {response.status_code}")
            if response.status_code == 401:
                logger.error("❌ Неверный Discord токен!")
            elif response.status_code == 403:
                logger.error("❌ Нет доступа к каналу!")
            return None
                
    except Exception as e:
        logger.error(f"💥 Ошибка при запросе к Discord: {e}")
        return None

def check_for_tomato(messages):
    """Проверяет сообщения на наличие томата"""
    global last_processed_id
    
    if not messages:
        return False
    
    # Сортируем сообщения от новых к старым
    messages.sort(key=lambda x: x['id'], reverse=True)
    
    found_tomato = False
    newest_id = messages[0]['id']
    
    # Если это первый запуск, запоминаем последнее сообщение
    if last_processed_id is None:
        last_processed_id = newest_id
        logger.info(f"🚀 Первый запуск. Запомнил сообщение: {last_processed_id}")
        return False
    
    # Проверяем только сообщения новее последнего обработанного
    for message in messages:
        message_id = message['id']
        
        # Если дошли до уже обработанных - выходим
        if message_id <= last_processed_id:
            break
        
        author = message.get('author', {}).get('username', '')
        content = message.get('content', '')
        
        logger.info(f"🔍 Проверяю сообщение {message_id} от {author}")
        
        # Проверяем сообщения от Ember бота
        if 'Ember' in author or 'Stock' in content:
            # Получаем весь текст из эмбедов
            full_text = content.lower()
            embeds = message.get('embeds', [])
            
            for embed in embeds:
                full_text += f" {embed.get('title', '').lower()}"
                full_text += f" {embed.get('description', '').lower()}"
                
                for field in embed.get('fields', []):
                    full_text += f" {field.get('name', '').lower()}"
                    full_text += f" {field.get('value', '').lower()}"
            
            logger.info(f"📄 Текст сообщения Ember: {full_text[:200]}...")
            
            # Ищем томат в любом виде
            if any(tomato in full_text for tomato in ['tomato', ':tomato', 'помидор', 'томат']):
                logger.info("🎯 ОБНАРУЖЕН ТОМАТ В СООБЩЕНИИ EMBER!")
                
                # Формируем красивое сообщение
                message_text = "🍅 <b>Томат в стоке!</b>\n"
                message_text += f"📅 Время: {datetime.now().strftime('%H:%M:%S')}\n"
                message_text += "🤖 От: Ember Bot"
                
                send_telegram(message_text)
                found_tomato = True
                break
    
    # Обновляем последнее обработанное сообщение
    last_processed_id = newest_id
    
    return found_tomato

def monitor_discord():
    """Основная функция мониторинга"""
    logger.info("🔄 Запуск мониторинга Discord...")
    
    error_count = 0
    max_errors = 5
    
    while True:
        try:
            messages = get_discord_messages()
            
            if messages is not None:
                found = check_for_tomato(messages)
                
                if found:
                    logger.info("✅ Уведомление о томате отправлено!")
                else:
                    logger.info("🔍 Томатов нет в новых сообщениях")
                
                error_count = 0  # Сброс счетчика ошибок
            else:
                error_count += 1
                logger.warning(f"⚠️ Ошибка получения сообщений ({error_count}/{max_errors})")
                
                if error_count >= max_errors:
                    logger.error("🚨 Слишком много ошибок, перезапуск через 5 минут...")
                    send_telegram("🚨 <b>ВНИМАНИЕ!</b>\nБот обнаружил проблемы с подключением к Discord.\nПерезапускаюсь...")
                    time.sleep(300)  # Ждем 5 минут перед повторной попыткой
                    error_count = 0
            
            # Ждем 30 секунд перед следующей проверкой
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в мониторинге: {e}")
            error_count += 1
            time.sleep(60)

def health_check():
    """Проверка здоровья бота - отправляет отчет каждые 6 часов"""
    while True:
        try:
            uptime = datetime.now() - startup_time
            hours = uptime.total_seconds() / 3600
            
            status_text = (
                f"🤖 <b>Статус бота</b>\n"
                f"⏰ Работает: {hours:.1f} часов\n"
                f"📅 Запущен: {startup_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"🔄 Мониторю: Ember bot → Tomato\n"
                f"✅ Все системы в норме"
            )
            
            send_telegram(status_text)
            logger.info("📊 Отчет о состоянии отправлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки отчета: {e}")
        
        # Ждем 6 часов (21600 секунд)
        time.sleep(21600)

@app.route('/')
def home():
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    return f"""
    <html>
        <head>
            <title>🍅 Tomato Monitor</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .status {{ background: #f0f8f0; padding: 20px; border-radius: 10px; }}
                .info {{ margin: 10px 0; }}
            </style>
        </head>
        <body>
            <h1>🍅 Мониторинг томатов</h1>
            <div class="status">
                <div class="info"><strong>Бот:</strong> Активен ✅</div>
                <div class="info"><strong>Время работы:</strong> {hours:.1f} часов</div>
                <div class="info"><strong>Запущен:</strong> {startup_time.strftime('%d.%m.%Y %H:%M:%S')}</div>
                <div class="info"><strong>Отслеживаю:</strong> Ember bot → Tomato</div>
                <div class="info"><strong>Последнее сообщение:</strong> {last_processed_id or 'Еще не проверял'}</div>
            </div>
            <p><a href="/test">Тестировать сейчас</a> | <a href="/status">Отправить статус</a></p>
        </body>
    </html>
    """

@app.route('/test')
def test():
    """Принудительная проверка"""
    messages = get_discord_messages()
    if messages:
        found = check_for_tomato(messages)
        return f"Проверка завершена: {'🎯 ТОМАТ НАЙДЕН!' if found else '🔍 Томатов нет'}"
    else:
        return "❌ Ошибка при получении сообщений"

@app.route('/status')
def status():
    """Отправляет статус в Telegram"""
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    status_text = (
        f"🔍 <b>Ручная проверка</b>\n"
        f"⏰ Работает: {hours:.1f} часов\n"
        f"📅 Запущен: {startup_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"🔄 Мониторю: Ember bot → Tomato\n"
        f"📝 Последнее сообщение: {last_processed_id or 'Еще не проверял'}\n"
        f"✅ Бот активен и работает"
    )
    
    success = send_telegram(status_text)
    return f"Статус: {'✅ Отправлен' if success else '❌ Ошибка'}"

# Запускаем мониторинг в отдельных потоках
threading.Thread(target=monitor_discord, daemon=True).start()
threading.Thread(target=health_check, daemon=True).start()

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК СУПЕР-НАДЕЖНОГО БОТА ДЛЯ EMBER!")
    logger.info("📊 Отслеживаю: Ember bot → Tomato")
    logger.info("🔄 Проверка каждые 30 секунд")
    logger.info("📡 Отчет о состоянии каждые 6 часов")
    
    # Отправляем сообщение о запуске
    startup_msg = "🚀 <b>Бот запущен!</b>\n📊 Начинаю мониторинг томатов от Ember бота\n⏰ Проверка каждые 30 секунд"
    send_telegram(startup_msg)
    
    app.run(host='0.0.0.0', port=5000)
