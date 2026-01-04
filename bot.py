from flask import Flask, request, jsonify
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
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
RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
API_URL = "https://gagapi.onrender.com/alldata"
CHECK_INTERVAL = 30  # секунд

# Хранилище последнего состояния ВСЕХ семян
last_all_seeds = {}
bot_start_time = datetime.now()
api_request_count = 0
last_error = None

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML", disable_notification=False):
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except:
        return False

def send_to_bot(text):
    if TELEGRAM_BOT_CHAT_ID:
        return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

def send_to_channel(text):
    if TELEGRAM_CHANNEL_ID:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text, disable_notification=True)

# ==================== ОСНОВНАЯ ПРОВЕРКА ====================
def check_all_seeds():
    """Проверяет ВСЕ семена из API"""
    global api_request_count, last_error, last_all_seeds
    
    try:
        api_request_count += 1
        current_time = datetime.now()
        
        logger.info(f"🔍 Проверка #{api_request_count} в {current_time.strftime('%H:%M:%S')}")
        
        response = requests.get(API_URL, timeout=10)
        
        if response.status_code != 200:
            last_error = f"API ошибка {response.status_code}"
            logger.error(f"❌ {last_error}")
            return None
        
        data = response.json()
        current_seeds = {}
        
        # Получаем ВСЕ семена
        for seed in data.get('seeds', []):
            name = seed.get('name', 'Без названия')
            quantity = seed.get('quantity', 0)
            current_seeds[name] = quantity
        
        logger.info(f"📊 Всего семян: {len(current_seeds)} видов")
        
        # Логируем все семена для отладки
        for name, qty in current_seeds.items():
            logger.info(f"   {name}: {qty} шт")
        
        return current_seeds
        
    except Exception as e:
        last_error = str(e)
        logger.error(f"💥 Ошибка: {e}")
        return None

def compare_seeds(old_seeds, new_seeds):
    """Сравнивает два состояния семян и возвращает изменения"""
    changes = []
    
    if not old_seeds or not new_seeds:
        return changes
    
    # Все имена семян
    all_names = set(list(old_seeds.keys()) + list(new_seeds.keys()))
    
    for name in all_names:
        old_qty = old_seeds.get(name, 0)
        new_qty = new_seeds.get(name, 0)
        
        if old_qty != new_qty:
            changes.append({
                'name': name,
                'old': old_qty,
                'new': new_qty,
                'change': new_qty - old_qty
            })
    
    return changes

def send_seed_report(all_seeds, changes=None):
    """Отправляет отчет о всех семенах"""
    if not all_seeds:
        return
    
    # Сортируем по количеству (от большего к меньшему)
    sorted_seeds = sorted(all_seeds.items(), key=lambda x: x[1], reverse=True)
    
    # Формируем сообщение
    report_lines = []
    report_lines.append("📊 <b>ВСЕ СЕМЕНА В ИГРЕ:</b>")
    report_lines.append("")
    
    for name, qty in sorted_seeds:
        if qty > 0:
            report_lines.append(f"🌱 <b>{name}</b>: {qty} шт")
        else:
            report_lines.append(f"⭕ {name}: {qty} шт")
    
    if changes:
        report_lines.append("")
        report_lines.append("🔄 <b>ИЗМЕНЕНИЯ:</b>")
        for change in changes:
            if change['change'] > 0:
                report_lines.append(f"📈 {change['name']}: {change['old']} → {change['new']} (+{change['change']})")
            else:
                report_lines.append(f"📉 {change['name']}: {change['old']} → {change['new']} ({change['change']})")
    
    report_lines.append("")
    report_lines.append(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    
    message = "\n".join(report_lines)
    
    # Отправляем в канал
    success = send_to_channel(message)
    
    if success:
        logger.info(f"📢 Отчет отправлен: {len(all_seeds)} семян")
    else:
        logger.error("❌ Ошибка отправки отчета")

# ==================== МОНИТОРИНГ ====================
def monitor_all_seeds():
    """Мониторит ВСЕ семена"""
    global last_all_seeds
    
    logger.info("🚀 Запуск мониторинга ВСЕХ семян")
    
    # Первая проверка
    current_seeds = check_all_seeds()
    if current_seeds:
        last_all_seeds = current_seeds
        send_seed_report(current_seeds)
    
    check_counter = 0
    
    while True:
        try:
            check_counter += 1
            
            # Проверяем
            current_seeds = check_all_seeds()
            
            if current_seeds:
                # Сравниваем с предыдущим состоянием
                changes = compare_seeds(last_all_seeds, current_seeds)
                
                if changes:
                    logger.info(f"🎯 Найдено изменений: {len(changes)}")
                    # Отправляем отчет только если есть изменения
                    send_seed_report(current_seeds, changes)
                    last_all_seeds = current_seeds
                else:
                    logger.info("📭 Изменений нет")
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"💥 Ошибка: {e}")
            time.sleep(10)

# ==================== ТЕСТОВЫЕ КОМАНДЫ ====================
def test_direct_api():
    """Тестирует прямое обращение к разным API"""
    test_urls = [
        "https://gagapi.onrender.com/seeds",
        "https://gagapi.onrender.com/alldata",
        "https://gagapi.onrender.com/gear"
    ]
    
    results = []
    
    for url in test_urls:
        try:
            logger.info(f"🧪 Тестирую {url}")
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                results.append(f"✅ {url}: {len(data) if isinstance(data, list) else 'JSON получен'}")
            else:
                results.append(f"❌ {url}: ошибка {response.status_code}")
        except Exception as e:
            results.append(f"💥 {url}: {e}")
    
    return results

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    tomato_qty = last_all_seeds.get('Tomato', 0) if last_all_seeds else 0
    
    return f"""
    <html>
    <head><title>Мониторинг всех семян</title><meta charset="utf-8"></head>
    <body>
        <h1>🧪 Мониторинг ВСЕХ семян</h1>
        
        <div style="background:#f0f8ff; padding:20px; border-radius:10px; margin:20px 0;">
            <h3>🎯 Текущее состояние</h3>
            <p><b>Запросов к API:</b> {api_request_count}</p>
            <p><b>Помидоры:</b> {tomato_qty} шт</p>
            <p><b>Всего семян:</b> {len(last_all_seeds) if last_all_seeds else 0} видов</p>
            <p><b>Интервал:</b> {CHECK_INTERVAL} секунд</p>
        </div>
        
        <div style="background:#fff3cd; padding:20px; border-radius:10px; margin:20px 0;">
            <h3>🔍 Тестирование API</h3>
            <p>Если API не обновляется, проблема в источнике данных.</p>
            <p>Попробуйте:</p>
            <ul>
                <li><a href="/test" target="_blank">Протестировать все эндпоинты API</a></li>
                <li><a href="/check" target="_blank">Принудительно проверить семена</a></li>
                <li><a href="/debug" target="_blank">Получить сырые данные API</a></li>
            </ul>
        </div>
        
        <div style="background:#e7f3ff; padding:20px; border-radius:10px; margin:20px 0;">
            <h3>📊 Последние семена</h3>
            <pre>{json.dumps(last_all_seeds, indent=2, ensure_ascii=False) if last_all_seeds else 'Нет данных'}</pre>
        </div>
    </body>
    </html>
    """

@app.route('/test')
def test_page():
    """Тестирует API"""
    results = test_direct_api()
    return "<br>".join(results)

@app.route('/check')
def check_page():
    """Принудительная проверка"""
    current_seeds = check_all_seeds()
    if current_seeds:
        changes = compare_seeds(last_all_seeds, current_seeds)
        send_seed_report(current_seeds, changes)
        return f"✅ Проверено. Изменений: {len(changes)}"
    return "❌ Ошибка проверки"

@app.route('/debug')
def debug_page():
    """Показывает сырые данные API"""
    try:
        response = requests.get(API_URL, timeout=10)
        return f"<pre>{json.dumps(response.json(), indent=2, ensure_ascii=False)}</pre>"
    except Exception as e:
        return f"❌ Ошибка: {e}"

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🌱 ЗАПУСК МОНИТОРИНГА ВСЕХ СЕМЯН")
    logger.info("=" * 60)
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=monitor_all_seeds, daemon=True)
    monitor_thread.start()
    
    # Запускаем Flask
    port = int(os.getenv('PORT', 10000))
    logger.info(f"🌐 Веб-сервер на порту {port}")
    
    # Отправляем тестовое сообщение
    send_to_bot("🌱 Бот мониторинга всех семян запущен!")
    
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
