from flask import Flask
import requests
import os
import time
import logging
import threading
from datetime import datetime
import json

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

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
API_URL = "https://gagapi.onrender.com/alldata"
last_raw_data = None
last_data_string = None
check_count = 0
bot_start_time = datetime.now()

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, json=data, timeout=5)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False

def send_to_channel(text):
    if TELEGRAM_CHANNEL_ID:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)

def send_to_bot(text):
    if TELEGRAM_BOT_CHAT_ID:
        return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

# ==================== ПРОВЕРКА API ====================
def get_api_data():
    """Получает ВСЕ данные из API"""
    global check_count
    
    try:
        check_count += 1
        logger.info(f"🔍 Проверка #{check_count} API...")
        
        response = requests.get(API_URL, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"❌ API ошибка: {response.status_code}")
            return None
        
        data = response.json()
        
        # Простой лог что получили
        logger.info(f"📦 Получены данные:")
        logger.info(f"   🕒 Время API: {data.get('lastGlobalUpdate', 'нет')}")
        
        # Считаем общее количество предметов
        total_items = 0
        for category in ['seeds', 'cosmetics', 'eggs', 'events', 'gear', 'honey']:
            items = data.get(category, [])
            if items:
                logger.info(f"   📊 {category}: {len(items)} предметов")
                total_items += len(items)
        
        logger.info(f"   Итого: {total_items} предметов")
        
        return data
        
    except Exception as e:
        logger.error(f"❌ Ошибка запроса: {e}")
        return None

def simple_compare(old_data, new_data):
    """Простое сравнение данных"""
    if not old_data or not new_data:
        return ["Нет данных для сравнения"]
    
    changes = []
    
    # Сравниваем время обновления
    old_time = old_data.get('lastGlobalUpdate', '')
    new_time = new_data.get('lastGlobalUpdate', '')
    
    if old_time != new_time:
        changes.append(f"🕒 Время обновления: {old_time} → {new_time}")
    
    # Простая проверка: количество предметов в каждой категории
    categories = ['seeds', 'cosmetics', 'eggs']
    
    for category in categories:
        old_items = old_data.get(category, [])
        new_items = new_data.get(category, [])
        
        if len(old_items) != len(new_items):
            changes.append(f"📊 {category}: было {len(old_items)}, стало {len(new_items)}")
        
        # Простая проверка помидоров
        if category == 'seeds':
            old_tomatoes = sum(1 for s in old_items if 'tomato' in s.get('name', '').lower())
            new_tomatoes = sum(1 for s in new_items if 'tomato' in s.get('name', '').lower())
            
            if old_tomatoes != new_tomatoes:
                changes.append(f"🍅 Помидоров: было {old_tomatoes}, стало {new_tomatoes}")
    
    return changes

# ==================== МОНИТОРИНГ ====================
def monitor_api():
    """Основной цикл мониторинга"""
    global last_raw_data, last_data_string
    
    logger.info("🚀 Запуск простого мониторинга API")
    
    # Первая проверка
    initial_data = get_api_data()
    if initial_data:
        last_raw_data = initial_data
        last_data_string = json.dumps(initial_data, sort_keys=True)
        logger.info("✅ Первые данные получены")
    
    check_interval = 60  # 1 минута
    
    while True:
        try:
            # Получаем новые данные
            new_data = get_api_data()
            
            if new_data and last_data_string:
                # Простое сравнение строк
                new_data_string = json.dumps(new_data, sort_keys=True)
                
                if new_data_string != last_data_string:
                    # Нашли изменения!
                    logger.info("🎯 ОБНАРУЖЕНЫ ИЗМЕНЕНИЯ!")
                    
                    # Анализируем что изменилось
                    changes = simple_compare(last_raw_data, new_data)
                    
                    # Формируем простое сообщение
                    if changes:
                        message_lines = ["🔔 <b>ИЗМЕНЕНИЯ В ДАННЫХ API:</b>"]
                        for change in changes:
                            message_lines.append(f"• {change}")
                        
                        message_lines.append("")
                        message_lines.append(f"⏰ Проверка: {check_count}")
                        message_lines.append(f"🕒 Время: {datetime.now().strftime('%H:%M:%S')}")
                        
                        message = "\n".join(message_lines)
                        
                        # Отправляем в канал
                        if send_to_channel(message):
                            logger.info(f"📢 Отправлено уведомление")
                        else:
                            logger.error("❌ Не удалось отправить в Telegram")
                    
                    # Обновляем сохранённые данные
                    last_data_string = new_data_string
                    last_raw_data = new_data
                else:
                    logger.info("📭 Изменений нет")
            elif new_data:
                # Первые данные
                last_data_string = json.dumps(new_data, sort_keys=True)
                last_raw_data = new_data
            
            # Ждём перед следующей проверкой
            time.sleep(check_interval)
            
        except Exception as e:
            logger.error(f"💥 Ошибка: {e}")
            time.sleep(30)

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    """Простая главная страница"""
    
    status = "🟢 Работает" if last_raw_data else "🟡 Загрузка..."
    
    if last_raw_data:
        update_time = last_raw_data.get('lastGlobalUpdate', 'нет')
        seeds_count = len(last_raw_data.get('seeds', []))
    else:
        update_time = "нет данных"
        seeds_count = 0
    
    return f"""
    <html>
    <head>
        <title>API Мониторинг</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial; margin: 20px; }}
            .info {{ background: #f0f0f0; padding: 15px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h1>🔍 Мониторинг данных игры</h1>
        
        <div class="info">
            <p><b>Статус:</b> {status}</p>
            <p><b>Проверок:</b> {check_count}</p>
            <p><b>Время API:</b> {update_time}</p>
            <p><b>Семян в игре:</b> {seeds_count} видов</p>
            <p><b>Работает:</b> {(datetime.now() - bot_start_time).total_seconds()/60:.0f} мин</p>
        </div>
        
        <p><a href="/data">Посмотреть данные</a> | <a href="/check">Проверить сейчас</a></p>
        
        <h3>Как работает:</h3>
        <ul>
            <li>Проверяет API каждую минуту</li>
            <li>Сравнивает с предыдущими данными</li>
            <li>Отправляет уведомления об изменениях</li>
        </ul>
    </body>
    </html>
    """

@app.route('/data')
def show_data():
    """Показывает сырые данные"""
    if last_raw_data:
        return f"<pre>{json.dumps(last_raw_data, indent=2, ensure_ascii=False)}</pre>"
    return "Нет данных"

@app.route('/check')
def check_now():
    """Принудительная проверка"""
    data = get_api_data()
    return jsonify({
        'checked': data is not None,
        'check_number': check_count,
        'time': datetime.now().isoformat()
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🔍 ЗАПУСК ПРОСТОГО МОНИТОРИНГА API")
    logger.info("=" * 50)
    
    # Запускаем мониторинг
    thread = threading.Thread(target=monitor_api, daemon=True)
    thread.start()
    
    # Сообщение о запуске
    try:
        send_to_bot("🔍 <b>Мониторинг API запущен</b>\nПроверяю данные каждую минуту...")
    except:
        pass
    
    # Запускаем Flask
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
