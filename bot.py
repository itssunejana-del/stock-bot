from flask import Flask, request, jsonify
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
import re
import json
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')

# Проверка переменных
REQUIRED_VARS = ['TELEGRAM_TOKEN', 'TELEGRAM_CHANNEL_ID', 'TELEGRAM_BOT_CHAT_ID']
missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
if missing:
    logger.error(f"❌ Отсутствуют переменные: {missing}")

# ==================== ОТСЛЕЖИВАЕМЫЕ ПРЕДМЕТЫ ====================
TARGET_ITEMS = {
    # 🍅 Только помидоры для теста
    'tomato': {
        'keywords': ['tomato', 'томат', 'помидор'],
        'display_name': '🍅 Помидор',
        'type': 'seed'
    }
}

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
# API конфигурация
API_URL = "https://gagapi.onrender.com/alldata"
CHECK_INTERVAL = 30  # секунд (2 запроса в минуту, лимит API - 5 запросов)

# Хранилище последнего состояния
last_api_state = {
    'tomato': {'quantity': 0, 'last_notified': None}
}

# Статистика
bot_start_time = datetime.now()
bot_status = "🟢 Инициализация через API"
api_request_count = 0
ping_count = 0
last_ping_time = None
found_items_count = {'tomato': 0}
telegram_offset = 0
last_error = None

# Файл для сохранения состояния
STATE_FILE = 'api_state.json'

# ==================== СОХРАНЕНИЕ СОСТОЯНИЯ ====================
def save_state():
    """Сохраняет состояние в файл"""
    try:
        state = {
            'last_api_state': last_api_state,
            'found_items_count': found_items_count,
            'api_request_count': api_request_count,
            'ping_count': ping_count,
            'bot_status': bot_status
        }
        
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, default=str)
        
        logger.debug("💾 Состояние API сохранено")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения состояния: {e}")

def load_state():
    """Загружает состояние из файла"""
    global last_api_state, found_items_count, api_request_count, ping_count, bot_status
    
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
            
            last_api_state = state.get('last_api_state', last_api_state)
            found_items_count = state.get('found_items_count', found_items_count)
            api_request_count = state.get('api_request_count', api_request_count)
            ping_count = state.get('ping_count', ping_count)
            bot_status = state.get('bot_status', bot_status)
            
            logger.info("💾 Состояние API загружено")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки состояния: {e}")

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML", disable_notification=False):
    """Отправляет сообщение в Telegram"""
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены Telegram переменные")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification
        }
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram, жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Ошибка Telegram {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def send_to_bot(text, disable_notification=False):
    """Отправляет сообщение в ТЕЛЕГРАМ БОТА"""
    if not TELEGRAM_BOT_CHAT_ID:
        return False
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text, disable_notification=disable_notification)

def send_to_channel(text, disable_notification=True):
    """Отправляет сообщение в канал"""
    if not TELEGRAM_CHANNEL_ID:
        return False
    return send_telegram_message(TELEGRAM_CHANNEL_ID, text, disable_notification=disable_notification)

def handle_telegram_command(chat_id, command, message=None):
    """Обрабатывает команды Telegram"""
    logger.info(f"🎯 Обрабатываю команду: {command} от {chat_id}")
    
    if command == '/start':
        welcome_text = (
            "🧪 <b>ТЕСТОВЫЙ БОТ API МОНИТОРИНГА</b>\n\n"
            "Я отслеживаю только 🍅 <b>помидоры</b> через прямой API игры.\n\n"
            "📊 <b>Текущая конфигурация:</b>\n"
            "• Отслеживаю: 🍅 Томаты (Tomato)\n"
            "• Источник: Прямой API игры (gagapi.onrender.com)\n"
            "• Интервал: Каждые 30 секунд\n"
            "• Уведомления: Текстовые (без стикеров)\n\n"
            f"📈 <b>Статистика:</b>\n"
            f"• Запросов к API: {api_request_count}\n"
            f"• Найдено помидоров: {found_items_count['tomato']}\n\n"
            "🎛️ <b>Команды:</b>\n"
            "/start - Эта информация\n"
            "/status - Подробный статус\n"
            "/test - Тестовое уведомление\n"
            "/check - Принудительная проверка API"
        )
        send_telegram_message(chat_id, welcome_text)
        
    elif command == '/status':
        uptime = datetime.now() - bot_start_time
        hours = uptime.total_seconds() / 3600
        
        tomato_state = last_api_state['tomato']
        last_notified = tomato_state['last_notified']
        last_notified_str = last_notified.strftime('%H:%M:%S') if last_notified else "никогда"
        
        status_text = (
            f"📊 <b>СТАТУС ТЕСТОВОГО БОТА API</b>\n\n"
            f"🟢 {bot_status}\n"
            f"⏰ Время работы: {hours:.1f} часов\n"
            f"📅 Запущен: {bot_start_time.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"🎯 <b>Отслеживаемый предмет:</b>\n"
            f"🍅 Помидор (Tomato)\n\n"
            f"📡 <b>API Статистика:</b>\n"
            f"• Запросов к API: {api_request_count}\n"
            f"• Интервал проверки: {CHECK_INTERVAL} секунд\n"
            f"• Последнее количество: {tomato_state['quantity']} шт\n"
            f"• Последнее уведомление: {last_notified_str}\n"
            f"• Всего найдено раз: {found_items_count['tomato']}\n\n"
            f"🔗 <b>Источник данных:</b>\n"
            f"• API: {API_URL}\n"
            f"• Обновление: в реальном времени\n"
            f"• Лимит: 5 запросов/минуту\n\n"
            f"📝 <b>Логика работы:</b>\n"
            f"1. Запрашиваем /alldata каждые {CHECK_INTERVAL} сек\n"
            f"2. Ищем Tomato в разделе seeds\n"
            f"3. Сравниваем количество с предыдущим\n"
            f"4. Если изменилось → отправляем уведомление\n"
            f"5. Защита от дублей: не уведомляем если количество не изменилось"
        )
        
        if last_error:
            status_text += f"\n\n⚠️ <b>Последняя ошибка:</b>\n<code>{last_error}</code>"
        
        send_telegram_message(chat_id, status_text)
        
    elif command == '/test':
        test_msg = (
            f"🧪 <b>ТЕСТОВОЕ УВЕДОМЛЕНИЕ</b>\n\n"
            f"Это тестовое сообщение от бота API мониторинга.\n"
            f"Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"Если вы видите это, бот работает корректно!"
        )
        send_telegram_message(chat_id, test_msg)
        
    elif command == '/check':
        # Принудительная проверка
        items_found = check_gag_api()
        if items_found:
            msg = f"✅ Проверка API выполнена. Найдено изменений: {len(items_found)}"
        else:
            msg = "ℹ️ Проверка API выполнена. Изменений не обнаружено."
        send_telegram_message(chat_id, msg)
        
    else:
        send_telegram_message(chat_id, "❌ Неизвестная команда. Используйте /start для списка команд.")

def telegram_poller():
    """Опросщик Telegram команд"""
    global telegram_offset
    
    logger.info("🔍 Запускаю Telegram поллер...")
    
    time.sleep(10)
    telegram_offset = 0
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {
                'offset': telegram_offset + 1,
                'timeout': 10,
                'limit': 1
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('ok') and data.get('result'):
                    updates = data['result']
                    
                    for update in updates:
                        telegram_offset = update['update_id']
                        
                        if 'message' in update:
                            message = update['message']
                            chat_id = message['chat']['id']
                            text = message.get('text', '')
                            
                            if text.startswith('/'):
                                handle_telegram_command(chat_id, text)
                
                time.sleep(5)
                
            elif response.status_code == 409:
                logger.warning("⚠️ Конфликт с другим экземпляром. Жду 60 секунд...")
                time.sleep(60)
            else:
                logger.error(f"❌ Ошибка Telegram API: {response.status_code}")
                time.sleep(10)
            
        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            logger.error(f"💥 Ошибка в телеграм поллере: {e}")
            time.sleep(10)

# ==================== API МОНИТОРИНГ ====================
def check_gag_api():
    """
    Проверяет API на наличие изменений в помидорах
    Возвращает список найденных изменений
    """
    global api_request_count, last_error, bot_status, found_items_count
    
    try:
        api_request_count += 1
        current_time = datetime.now()
        
        logger.debug(f"🔍 Проверяю API (#{api_request_count})...")
        
        # Делаем запрос к API
        response = requests.get(API_URL, timeout=10)
        
        if response.status_code != 200:
            last_error = f"API ошибка {response.status_code}"
            logger.error(f"❌ {last_error}")
            return []
        
        data = response.json()
        
        # Ищем помидоры в разделе seeds
        current_tomato_qty = 0
        
        for seed in data.get('seeds', []):
            name = seed.get('name', '').lower()
            if 'tomato' in name:
                current_tomato_qty = seed.get('quantity', 0)
                break
        
        # Получаем предыдущее состояние
        prev_state = last_api_state['tomato']
        prev_qty = prev_state['quantity']
        last_notified = prev_state.get('last_notified')
        
        # Проверяем изменения
        items_found = []
        
        if current_tomato_qty != prev_qty:
            # Изменение обнаружено!
            logger.info(f"🎯 Изменение помидоров: {prev_qty} → {current_tomato_qty}")
            
            # Защита от дублей: проверяем, когда было последнее уведомление
            should_notify = True
            if last_notified:
                time_since_last = (current_time - last_notified).total_seconds()
                # Если прошло меньше 10 секунд - вероятно дубль
                if time_since_last < 10 and prev_qty == 0 and current_tomato_qty > 0:
                    logger.debug(f"⏭️ Пропускаем возможный дубль (прошло {time_since_last:.1f} сек)")
                    should_notify = False
            
            if should_notify:
                items_found.append({
                    'name': 'tomato',
                    'quantity': current_tomato_qty,
                    'previous_quantity': prev_qty,
                    'type': 'seed',
                    'timestamp': current_time
                })
                
                found_items_count['tomato'] += 1
                
                # Обновляем состояние с временем уведомления
                last_api_state['tomato'] = {
                    'quantity': current_tomato_qty,
                    'last_notified': current_time
                }
                
                bot_status = f"🍅 Помидоры: {current_tomato_qty} шт"
            else:
                # Обновляем только количество, без времени уведомления
                last_api_state['tomato']['quantity'] = current_tomato_qty
        
        elif current_tomato_qty == 0:
            bot_status = f"📭 Помидоров нет в стоке"
        else:
            bot_status = f"🍅 Помидоров: {current_tomato_qty} шт (без изменений)"
        
        last_error = None
        return items_found
        
    except requests.exceptions.Timeout:
        last_error = "Таймаут запроса к API"
        logger.warning("⏰ Таймаут API")
        return []
    except requests.exceptions.RequestException as e:
        last_error = f"Ошибка запроса: {e}"
        logger.error(f"❌ Ошибка API запроса: {e}")
        return []
    except Exception as e:
        last_error = f"Неизвестная ошибка: {e}"
        logger.error(f"💥 Неизвестная ошибка API: {e}")
        return []

def send_tomato_notification(item_data):
    """Отправляет уведомление о помидорах"""
    quantity = item_data['quantity']
    prev_qty = item_data['previous_quantity']
    timestamp = item_data['timestamp']
    
    # Формируем сообщение
    if prev_qty == 0 and quantity > 0:
        # Появились в стоке
        message = (
            f"🎯 <b>ПОМИДОРЫ ПОЯВИЛИСЬ!</b>\n\n"
            f"🍅 <b>Томаты (Tomato)</b>\n"
            f"📦 Количество: <b>{quantity} шт</b>\n"
            f"🕒 Время: {timestamp.strftime('%H:%M:%S')}\n\n"
            f"✅ Быстро проверьте игру!"
        )
    elif quantity > prev_qty:
        # Количество увеличилось
        message = (
            f"📈 <b>БОЛЬШЕ ПОМИДОРОВ!</b>\n\n"
            f"🍅 <b>Томаты (Tomato)</b>\n"
            f"📦 Было: {prev_qty} шт\n"
            f"📦 Стало: <b>{quantity} шт</b>\n"
            f"🔼 Добавилось: {quantity - prev_qty} шт\n"
            f"🕒 Время: {timestamp.strftime('%H:%M:%S')}"
        )
    elif quantity < prev_qty:
        # Количество уменьшилось
        message = (
            f"📉 <b>МЕНЬШЕ ПОМИДОРОВ!</b>\n\n"
            f"🍅 <b>Томаты (Tomato)</b>\n"
            f"📦 Было: {prev_qty} шт\n"
            f"📦 Стало: <b>{quantity} шт</b>\n"
            f"🔽 Убавилось: {prev_qty - quantity} шт\n"
            f"🕒 Время: {timestamp.strftime('%H:%M:%S')}\n\n"
            f"⚡ Кто-то купил!"
        )
    else:
        # На всякий случай
        message = (
            f"ℹ️ <b>ИЗМЕНЕНИЕ ПОМИДОРОВ</b>\n\n"
            f"🍅 Количество: {quantity} шт\n"
            f"🕒 Время: {timestamp.strftime('%H:%M:%S')}"
        )
    
    # Отправляем в канал (текстовое сообщение)
    success = send_to_channel(message)
    
    # Также отправляем в бота для логов
    send_to_bot(f"🍅 Уведомление отправлено в канал: {quantity} шт")
    
    if success:
        logger.info(f"📢 Уведомление отправлено: помидоры {quantity} шт")
    else:
        logger.error("❌ Ошибка отправки уведомления")

# ==================== МОНИТОРЫ ====================
def monitor_api():
    """Основной цикл мониторинга API"""
    logger.info(f"🚀 Запуск мониторинга API (каждые {CHECK_INTERVAL} секунд)")
    
    # Первая проверка для инициализации состояния
    initial_check = check_gag_api()
    if initial_check:
        for item in initial_check:
            send_tomato_notification(item)
    
    logger.info("✅ Мониторинг API запущен")
    
    while True:
        try:
            # Проверяем API
            found_items = check_gag_api()
            
            # Обрабатываем найденные изменения
            if found_items:
                for item in found_items:
                    send_tomato_notification(item)
            
            # Сохраняем состояние
            save_state()
            
            # Ждём перед следующей проверкой
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторинге API: {e}")
            time.sleep(10)

def self_pinger():
    """Самопинг чтобы Render не останавливал сервис"""
    global ping_count, last_ping_time
    
    logger.info("🏓 Запуск самопинга (каждые 8 минут)")
    
    time.sleep(30)
    
    while True:
        try:
            ping_count += 1
            last_ping_time = datetime.now()
            logger.info(f"🏓 Самопинг #{ping_count}...")
            
            response = requests.get(f"{RENDER_SERVICE_URL}/", timeout=10)
            if response.status_code == 200:
                logger.info("✅ Самопинг успешен")
            else:
                logger.warning(f"⚠️ Самопинг: статус {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
        
        time.sleep(480)  # 8 минут

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    uptime = datetime.now() - bot_start_time
    uptime_str = str(uptime).split('.')[0]
    
    tomato_state = last_api_state['tomato']
    last_notified = tomato_state['last_notified']
    last_notified_str = last_notified.strftime('%H:%M:%S') if last_notified else "никогда"
    
    return f"""
    <html>
    <head>
        <title>🧪 Тестовый бот API мониторинга</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f0f8ff; }}
            .card {{ background: white; padding: 20px; border-radius: 15px; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .tomato {{ color: #e74c3c; font-weight: bold; }}
            .status {{ padding: 10px; border-radius: 5px; background: #2ecc71; color: white; display: inline-block; }}
        </style>
    </head>
    <body>
        <h1>🧪 Тестовый бот API мониторинга</h1>
        
        <div class="card">
            <h2>🎯 Отслеживаемый предмет</h2>
            <p class="tomato">🍅 Помидор (Tomato)</p>
            <p><strong>Текущее количество:</strong> <span class="tomato">{tomato_state['quantity']} шт</span></p>
            <p><strong>Последнее уведомление:</strong> {last_notified_str}</p>
            <p><strong>Всего найдено раз:</strong> {found_items_count['tomato']}</p>
        </div>
        
        <div class="card">
            <h2>📊 Статистика системы</h2>
            <p><strong>Статус:</strong> <span class="status">{bot_status}</span></p>
            <p><strong>Время работы:</strong> {uptime_str}</p>
            <p><strong>Запросов к API:</strong> {api_request_count}</p>
            <p><strong>Самопингов:</strong> {ping_count}</p>
            <p><strong>Запущен:</strong> {bot_start_time.strftime('%d.%m.%Y %H:%M:%S')}</p>
        </div>
        
        <div class="card">
            <h2>🔗 Источник данных</h2>
            <p><strong>API URL:</strong> {API_URL}</p>
            <p><strong>Интервал проверки:</strong> каждые {CHECK_INTERVAL} секунд</p>
            <p><strong>Лимит API:</strong> 5 запросов в минуту</p>
            <p><strong>Тип уведомлений:</strong> Текстовые сообщения (без стикеров)</p>
        </div>
        
        <div class="card">
            <h2>🛡️ Защита от дублей</h2>
            <p><strong>Логика работы:</strong></p>
            <ol>
                <li>Сравниваем количество с предыдущей проверкой</li>
                <li>Если изменилось → отправляем уведомление</li>
                <li>Сохраняем время последнего уведомления</li>
                <li>Не уведомляем, если изменение слишком быстрое (&lt;10 сек)</li>
                <li>Состояние сохраняется в файл и переживает перезапуски</li>
            </ol>
        </div>
        
        <div class="card">
            <h2>⚡ Скорость обновления</h2>
            <p><strong>Тестируем задержки:</strong></p>
            <ul>
                <li>API получает данные из игры в реальном времени</li>
                <li>Запросы каждые 30 секунд → почти мгновенное обнаружение</li>
                <li>Telegram отправляет уведомления за 1-3 секунды</li>
                <li><strong>Общая задержка: ~30-35 секунд</strong> от появления в игре до уведомления</li>
            </ul>
        </div>
    </body>
    </html>
    """

@app.route('/check_now')
def check_now():
    """Принудительная проверка API"""
    items = check_gag_api()
    return jsonify({
        'status': 'checked',
        'found_items': len(items),
        'tomato_quantity': last_api_state['tomato']['quantity'],
        'timestamp': datetime.now().isoformat()
    })

@app.route('/status')
def status_api():
    """API статуса"""
    return jsonify({
        'status': 'running',
        'bot_status': bot_status,
        'tomato': last_api_state['tomato'],
        'api_request_count': api_request_count,
        'found_items_count': found_items_count,
        'uptime_seconds': (datetime.now() - bot_start_time).total_seconds(),
        'check_interval': CHECK_INTERVAL,
        'last_ping': last_ping_time.isoformat() if last_ping_time else None
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    load_state()
    
    logger.info("=" * 60)
    logger.info("🧪 ЗАПУСК ТЕСТОВОГО БОТА API МОНИТОРИНГА")
    logger.info("=" * 60)
    logger.info("🎯 Отслеживаю только: 🍅 Помидор (Tomato)")
    logger.info("🔗 Источник: Прямой API игры (gagapi.onrender.com)")
    logger.info(f"⏰ Интервал проверки: каждые {CHECK_INTERVAL} секунд")
    logger.info("📢 Уведомления: Текстовые сообщения")
    logger.info("🛡️ Защита от дублей: включена")
    logger.info("💾 Сохранение состояния: включено")
    logger.info("=" * 60)
    
    threads = [
        threading.Thread(target=monitor_api, name='ApiMonitor', daemon=True),
        threading.Thread(target=self_pinger, name='SelfPinger', daemon=True),
        threading.Thread(target=telegram_poller, name='TelegramPoller', daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Запущен поток: {thread.name}")
        time.sleep(1)
    
    # Отправляем сообщение о запуске
    startup_msg = (
        f"🧪 <b>ТЕСТОВЫЙ БОТ API ЗАПУЩЕН</b>\n\n"
        f"🎯 <b>Конфигурация:</b>\n"
        f"• Отслеживаю: 🍅 Только помидоры (Tomato)\n"
        f"• Источник: Прямой API игры\n"
        f"• Интервал: каждые {CHECK_INTERVAL} секунд\n"
        f"• Уведомления: Текстовые сообщения\n\n"
        f"⚡ <b>Скорость работы:</b>\n"
        f"• API обновляется в реальном времени\n"
        f"• Проверка каждые {CHECK_INTERVAL} секунд\n"
        f"• Задержка уведомления: ~30-35 секунд\n\n"
        f"🛡️ <b>Защита от дублей:</b>\n"
        f"• Сравниваем количество с предыдущим\n"
        f"• Не уведомляем о быстрых повторениях\n"
        f"• Состояние сохраняется при перезапуске\n\n"
        f"📊 <b>Текущее состояние:</b>\n"
        f"🍅 Помидоры: {last_api_state['tomato']['quantity']} шт\n\n"
        f"✅ Бот начал мониторинг. Следите за каналом!"
    )
    send_to_bot(startup_msg)
    
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
