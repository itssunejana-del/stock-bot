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

# Токены и ID
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')  # Канал для томатов
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')  # Личные сообщения с ботом
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

# Глобальные переменные
last_processed_id = None
startup_time = datetime.now()

def send_telegram_message(chat_id, text, parse_mode="HTML"):
    """Отправляет сообщение в указанный чат/канал"""
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены переменные Telegram")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id, 
            "text": text,
            "parse_mode": parse_mode
        }
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено в Telegram ({chat_id}): {text[:100]}...")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def send_to_channel(text):
    """Отправляет сообщение в ТЕЛЕГРАМ КАНАЛ (только томаты)"""
    return send_telegram_message(TELEGRAM_CHANNEL_ID, text)

def send_to_bot(text):
    """Отправляет сообщение в ТЕЛЕГРАМ БОТА (все уведомления)"""
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

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
            error_msg = f"🚨 <b>Ошибка Discord</b>\nКод: {response.status_code}\n"
            if response.status_code == 401:
                error_msg += "❌ Неверный Discord токен!"
            elif response.status_code == 403:
                error_msg += "❌ Нет доступа к каналу!"
            else:
                error_msg += "❌ Неизвестная ошибка API"
            
            send_to_bot(error_msg)
            return None
                
    except Exception as e:
        logger.error(f"💥 Ошибка при запросе к Discord: {e}")
        send_to_bot(f"🚨 <b>Критическая ошибка</b>\nНе удалось подключиться к Discord:\n<code>{e}</code>")
        return None

def format_ember_message(message):
    """Форматирует сообщение от Ember для Telegram"""
    content = message.get('content', '')
    embeds = message.get('embeds', [])
    
    # Собираем весь текст
    full_text = content
    for embed in embeds:
        full_text += f"\n{embed.get('title', '')}"
        full_text += f"\n{embed.get('description', '')}"
        
        for field in embed.get('fields', []):
            full_text += f"\n{field.get('name', '')}: {field.get('value', '')}"
    
    return full_text

def check_ember_messages(messages):
    """Проверяет сообщения от Ember бота"""
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
        send_to_bot("🚀 <b>Бот запущен и начал мониторинг!</b>")
        return False
    
    # Проверяем только сообщения новее последнего обработанного
    for message in messages:
        message_id = message['id']
        
        # Если дошли до уже обработанных - выходим
        if message_id <= last_processed_id:
            break
        
        author = message.get('author', {}).get('username', '')
        
        # Проверяем только сообщения от Ember бота
        if 'Ember' in author:
            logger.info(f"🔍 Новое сообщение от Ember: {message_id}")
            
            # Форматируем сообщение для Telegram
            formatted_message = format_ember_message(message)
            message_preview = formatted_message[:300] + "..." if len(formatted_message) > 300 else formatted_message
            
            # Отправляем ВСЕ сообщения Ember в бота
            bot_message = (
                f"🤖 <b>Новое сообщение от Ember</b>\n"
                f"📅 ID: <code>{message_id}</code>\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
                f"📄 Содержание:\n<code>{message_preview}</code>"
            )
            send_to_bot(bot_message)
            
            # Проверяем на наличие томата (для канала)
            full_text = formatted_message.lower()
            if any(tomato in full_text for tomato in ['tomato', ':tomato']):
                logger.info("🎯 ОБНАРУЖЕН ТОМАТ В СООБЩЕНИИ EMBER!")
                
                # Отправляем в КАНАЛ
                channel_message = (
                    f"🍅 <b>Томат в стоке!</b>\n"
                    f"📅 Время: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"🤖 От: Ember Bot\n"
                    f"🆔 ID: {message_id}"
                )
                send_to_channel(channel_message)
                found_tomato = True
    
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
                found_tomato = check_ember_messages(messages)
                
                if found_tomato:
                    logger.info("✅ Уведомление о томате отправлено в канал!")
                else:
                    logger.info("🔍 Новых сообщений Ember обработано")
                
                error_count = 0  # Сброс счетчика ошибок
            else:
                error_count += 1
                logger.warning(f"⚠️ Ошибка получения сообщений ({error_count}/{max_errors})")
                
                if error_count >= max_errors:
                    logger.error("🚨 Слишком много ошибок, перезапуск через 5 минут...")
                    send_to_bot("🚨 <b>ВНИМАНИЕ!</b>\nБот обнаружил проблемы с подключением к Discord.\nПерезапускаюсь через 5 минут...")
                    time.sleep(300)  # Ждем 5 минут перед повторной попыткой
                    error_count = 0
            
            # Ждем 30 секунд перед следующей проверкой
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в мониторинге: {e}")
            send_to_bot(f"🚨 <b>Критическая ошибка!</b>\nВ мониторинге:\n<code>{e}</code>")
            error_count += 1
            time.sleep(60)

def health_check():
    """Проверка здоровья бота - отправляет отчет каждые 6 часов"""
    while True:
        try:
            uptime = datetime.now() - startup_time
            hours = uptime.total_seconds() / 3600
            
            status_text = (
                f"📊 <b>Статус бота</b>\n"
                f"⏰ Работает: {hours:.1f} часов\n"
                f"📅 Запущен: {startup_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"🔄 Мониторю: Ember bot\n"
                f"📢 Канал: Уведомления о томатах\n"
                f"🤖 Бот: Все сообщения + ошибки\n"
                f"✅ Все системы в норме"
            )
            
            send_to_bot(status_text)
            logger.info("📊 Отчет о состоянии отправлен боту")
            
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
                .channel {{ background: #e3f2fd; padding: 15px; margin: 10px 0; border-radius: 8px; }}
                .bot {{ background: #f3e5f5; padding: 15px; margin: 10px 0; border-radius: 8px; }}
            </style>
        </head>
        <body>
            <h1>🍅 Умный мониторинг томатов</h1>
            
            <div class="status">
                <div class="info"><strong>Бот:</strong> Активен ✅</div>
                <div class="info"><strong>Время работы:</strong> {hours:.1f} часов</div>
                <div class="info"><strong>Запущен:</strong> {startup_time.strftime('%d.%m.%Y %H:%M:%S')}</div>
                <div class="info"><strong>Отслеживаю:</strong> Ember bot</div>
                <div class="info"><strong>Последнее сообщение:</strong> {last_processed_id or 'Еще не проверял'}</div>
            </div>
            
            <div class="channel">
                <h3>📢 Телеграм КАНАЛ</h3>
                <p>Получает: <strong>Только уведомления о томатах</strong></p>
                <p>Для: Быстрые оповещения о стоках</p>
            </div>
            
            <div class="bot">
                <h3>🤖 Телеграм БОТ</h3>
                <p>Получает: <strong>Все сообщения Ember + ошибки + статусы</strong></p>
                <p>Для: Полный мониторинг и отладка</p>
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
        found = check_ember_messages(messages)
        return f"Проверка завершена: {'🎯 ТОМАТ НАЙДЕН!' if found else '🔍 Томатов нет, но сообщения обработаны'}"
    else:
        return "❌ Ошибка при получении сообщений"

@app.route('/status')
def status():
    """Отправляет статус в Telegram бота"""
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    status_text = (
        f"🔍 <b>Ручная проверка статуса</b>\n"
        f"⏰ Работает: {hours:.1f} часов\n"
        f"📅 Запущен: {startup_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"🔄 Мониторю: Ember bot\n"
        f"📝 Последнее сообщение: {last_processed_id or 'Еще не проверял'}\n"
        f"✅ Бот активен и работает"
    )
    
    success = send_to_bot(status_text)
    return f"Статус: {'✅ Отправлен боту' if success else '❌ Ошибка'}"

# Запускаем мониторинг в отдельных потоках
threading.Thread(target=monitor_discord, daemon=True).start()
threading.Thread(target=health_check, daemon=True).start()

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК УМНОГО БОТА С РАЗДЕЛЕНИЕМ УВЕДОМЛЕНИЙ!")
    logger.info("📢 Канал: Только томаты")
    logger.info("🤖 Бот: Все сообщения + ошибки + статусы")
    logger.info("🔄 Проверка каждые 30 секунд")
    
    # Отправляем сообщения о запуске
    startup_msg_channel = "🚀 <b>Мониторинг запущен!</b>\n📢 Этот канал будет получать только уведомления о томатах\n🍅 Ожидайте оповещений!"
    startup_msg_bot = (
        "🚀 <b>Бот запущен!</b>\n\n"
        "🤖 <b>Я буду присылать:</b>\n"
        "• Все сообщения от Ember бота\n"
        "• Ошибки и проблемы\n" 
        "• Статусы каждые 6 часов\n"
        "• Уведомления о перезапусках\n\n"
        "📊 <b>Начинаю мониторинг...</b>"
    )
    
    send_to_channel(startup_msg_channel)
    send_to_bot(startup_msg_bot)
    
    app.run(host='0.0.0.0', port=5000)
