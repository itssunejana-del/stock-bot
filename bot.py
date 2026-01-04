from flask import Flask
import requests
import os
import time
import logging
import threading
from datetime import datetime
import json
import hashlib

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
last_data_hash = None  # Хэш последних данных для сравнения
last_raw_data = None   # Сырые данные
check_count = 0        # Счётчик проверок
bot_start_time = datetime.now()

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, json=data, timeout=5)
        return response.status_code == 200
    except:
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
        
        response = requests.get(API_URL, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"❌ API ошибка: {response.status_code}")
            return None
        
        data = response.json()
        
        # Логируем что получили
        logger.info(f"📦 Получены данные:")
        logger.info(f"   🕒 Время обновления: {data.get('lastGlobalUpdate', 'нет')}")
        logger.info(f"   🌱 Семена: {len(data.get('seeds', []))} видов")
        logger.info(f"   💄 Косметика: {len(data.get('cosmetics', []))} видов")
        logger.info(f"   🥚 Яйца: {len(data.get('eggs', []))} видов")
        logger.info(f"   🎪 Ивенты: {len(data.get('events', []))} видов")
        
        return data
        
    except Exception as e:
        logger.error(f"❌ Ошибка запроса: {e}")
        return None

def calculate_data_hash(data):
    """Создаёт хэш данных для сравнения"""
    if not data:
        return None
    
    # Создаём строку для хэширования (исключаем timestamp для чистого сравнения)
    data_str = json.dumps(data, sort_keys=True)
    return hashlib.md5(data_str.encode()).hexdigest()

def compare_data(old_data, new_data):
    """Сравнивает два набора данных и возвращает различия"""
    if not old_data or not new_data:
        return "Нет данных для сравнения"
    
    changes = []
    
    # Сравниваем каждую категорию
    categories = ['seeds', 'cosmetics', 'eggs', 'events', 'gear', 'honey']
    
    for category in categories:
        old_items = old_data.get(category, [])
        new_items = new_data.get(category, [])
        
        # Преобразуем в словари для сравнения
        old_dict = {item.get('name', ''): item.get('quantity', 0) for item in old_items}
        new_dict = {item.get('name', ''): item.get('quantity', 0) for item in new_items}
        
        # Все уникальные имена
        all_names = set(list(old_dict.keys()) + list(new_dict.keys()))
        
        for name in all_names:
            old_qty = old_dict.get(name, 0)
            new_qty = new_dict.get(name, 0)
            
            if old_qty != new_qty:
                if old_qty == 0 and new_qty > 0:
                    changes.append(f"➕ {category}: {name} ПОЯВИЛСЯ ({new_qty} шт)")
                elif new_qty == 0 and old_qty > 0:
                    changes.append(f"➖ {category}: {name} ЗАКОНЧИЛСЯ (было {old_qty} шт)")
                else:
                    changes.append(f"📊 {category}: {name} {old_qty} → {new_qty} шт")
    
    # Время обновления
    old_time = old_data.get('lastGlobalUpdate', 'нет')
    new_time = new_data.get('lastGlobalUpdate', 'нет')
    
    if old_time != new_time:
        changes.append(f"🕒 Время обновления API: {old_time} → {new_time}")
    
    return changes

# ==================== МОНИТОРИНГ ====================
def monitor_api():
    """Основной цикл мониторинга ВСЕХ данных"""
    global last_data_hash, last_raw_data
    
    logger.info("🚀 Запуск мониторинга ВСЕХ данных игры")
    
    # Первая проверка
    initial_data = get_api_data()
    if initial_data:
        last_raw_data = initial_data
        last_data_hash = calculate_data_hash(initial_data)
        logger.info("✅ Первые данные получены и сохранены")
    
    check_interval = 60  # 1 минута - безопасно
    
    while True:
        try:
            # Получаем новые данные
            new_data = get_api_data()
            
            if new_data:
                # Сравниваем с предыдущими
                new_hash = calculate_data_hash(new_data)
                
                if last_data_hash and new_hash != last_data_hash:
                    # НАШЛИ ИЗМЕНЕНИЯ!
                    logger.info("🎯 ОБНАРУЖЕНЫ ИЗМЕНЕНИЯ В ДАННЫХ!")
                    
                    # Анализируем что изменилось
                    changes = compare_data(last_raw_data, new_data)
                    
                    # Формируем сообщение
                    if changes:
                        message_lines = ["🔔 <b>ИЗМЕНЕНИЯ В ИГРЕ:</b>"]
                        for change in changes[:10]:  # Первые 10 изменений
                            message_lines.append(f"• {change}")
                        
                        if len(changes) > 10:
                            message_lines.append(f"... и ещё {len(changes) - 10} изменений")
                        
                        message_lines.append("")
                        message_lines.append(f"🕒 Время: {datetime.now().strftime('%H:%M:%S')}")
                        message_lines.append(f"📡 API обновлён: {new_data.get('lastGlobalUpdate', 'нет')}")
                        
                        message = "\n".join(message_lines)
                        
                        # Отправляем в канал
                        send_to_channel(message)
                        logger.info(f"📢 Отправлено уведомление о {len(changes)} изменениях")
                    
                    # Обновляем сохранённые данные
                    last_data_hash = new_hash
                    last_raw_data = new_data
                else:
                    logger.info("📭 Изменений нет")
            
            # Ждём перед следующей проверкой
            logger.info(f"⏳ Следующая проверка через {check_interval} секунд...")
            time.sleep(check_interval)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в мониторинге: {e}")
            time.sleep(30)

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    """Главная страница с текущими данными"""
    
    # Текущая статистика
    if last_raw_data:
        seeds = last_raw_data.get('seeds', [])
        tomatoes = next((s for s in seeds if 'tomato' in s.get('name', '').lower()), None)
        tomato_count = tomatoes.get('quantity', 0) if tomatoes else 0
        
        status_html = f"""
        <div style="background:#f0f8ff;padding:20px;border-radius:10px;margin:20px 0;">
            <h2>📊 Текущие данные из игры</h2>
            <p>🕒 Последнее обновление API: {last_raw_data.get('lastGlobalUpdate', 'нет')}</p>
            <p>🍅 Помидоров в игре: {tomato_count} шт</p>
            <p>🌱 Всего семян: {len(seeds)} видов</p>
            <p>💄 Косметики: {len(last_raw_data.get('cosmetics', []))} видов</p>
            <p>🔍 Проверок: {check_count}</p>
            <p>⏰ Работает: {(datetime.now() - bot_start_time).total_seconds()/3600:.1f} ч</p>
        </div>
        
        <div style="background:#fff3cd;padding:20px;border-radius:10px;margin:20px 0;">
            <h3>🎯 Примеры семян:</h3>
            <pre style="max-height:200px;overflow:auto;">
{json.dumps(seeds[:10], indent=2, ensure_ascii=False) if seeds else 'Нет данных'}
            </pre>
        </div>
        """
    else:
        status_html = "<p style='color:red;'>❌ Данные ещё не получены</p>"
    
    return f"""
    <html>
    <head>
        <title>🎮 Мониторинг ВСЕХ данных игры</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .card {{ background: white; padding: 20px; border-radius: 10px; margin: 20px 0; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            button {{ padding: 10px 20px; background: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; }}
            button:hover {{ background: #45a049; }}
        </style>
    </head>
    <body>
        <h1>🎮 Мониторинг ВСЕХ данных игры</h1>
        
        {status_html}
        
        <div class="card">
            <h3>⚡ Как работает:</h3>
            <ol>
                <li>Запрашивает <b>ВСЕ данные</b> из API каждую минуту</li>
                <li>Сравнивает с предыдущими данными</li>
                <li>Отправляет уведомление при <b>ЛЮБОМ изменении</b></li>
                <li>Показывает что вообще происходит в игре</li>
            </ol>
            <p><b>Цель:</b> понять, обновляется ли API вообще</p>
        </div>
        
        <div class="card">
            <h3>🔧 Тестирование:</h3>
            <button onclick="checkNow()">🔄 Проверить сейчас</button>
            <button onclick="viewRawData()">📄 Показать сырые данные</button>
            <div id="result" style="margin-top:10px;"></div>
        </div>
        
        <script>
            function checkNow() {{
                fetch('/check')
                    .then(r => r.json())
                    .then(data => {{
                        document.getElementById('result').innerHTML = 
                            `<p>✅ Проверено. Хэш данных: ${data.hash?.substring(0, 8) || 'нет'}</p>`;
                    }});
            }}
            
            function viewRawData() {{
                fetch('/raw')
                    .then(r => r.text())
                    .then(text => {{
                        document.getElementById('result').innerHTML = 
                            `<pre style="max-height:300px;overflow:auto;">${{text}}</pre>`;
                    }});
            }}
        </script>
    </body>
    </html>
    """

@app.route('/check')
def check_now():
    """Принудительная проверка"""
    data = get_api_data()
    current_hash = calculate_data_hash(data) if data else None
    return jsonify({
        'status': 'checked',
        'hash': current_hash,
        'check_count': check_count,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/raw')
def raw_data():
    """Сырые данные API"""
    if last_raw_data:
        return json.dumps(last_raw_data, indent=2, ensure_ascii=False)
    return "Нет данных"

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🎮 ЗАПУСК МОНИТОРИНГА ВСЕХ ДАННЫХ ИГРЫ")
    logger.info("=" * 60)
    logger.info("📡 API: https://gagapi.onrender.com/alldata")
    logger.info("⏰ Интервал: 60 секунд")
    logger.info("🎯 Цель: отследить ЛЮБЫЕ изменения в данных")
    logger.info("=" * 60)
    
    # Запускаем мониторинг
    monitor_thread = threading.Thread(target=monitor_api, daemon=True)
    monitor_thread.start()
    logger.info("✅ Мониторинг запущен")
    
    # Сообщение о запуске
    startup_msg = (
        "🎮 <b>МОНИТОРИНГ ВСЕХ ДАННЫХ ЗАПУЩЕН</b>\n\n"
        "📡 <b>Что делаю:</b>\n"
        "• Запрашиваю ВСЕ данные из игры каждую минуту\n"
        "• Сравниваю с предыдущими данными\n"
        "• Отправляю уведомление при ЛЮБОМ изменении\n\n"
        "🎯 <b>Цель:</b>\n"
        "Узнать, обновляется ли API вообще\n"
        "Что меняется в данных игры\n"
        "Как часто происходят изменения\n\n"
        "✅ <b>Когда данные в игре изменятся</b> - вы получите уведомление!"
    )
    send_to_bot(startup_msg)
    
    # Запускаем Flask
    port = int(os.getenv('PORT', 10000))
    logger.info(f"🌐 Веб-сервер на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
