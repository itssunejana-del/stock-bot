from flask import Flask, jsonify
import asyncio
import websockets
import json
import threading
import time
from datetime import datetime
import logging
import os
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')

# WebSocket URL с нового сервера
WEBSOCKET_URL = "wss://websocket.joshlei.com/growagarden?user_id=monitor_bot"

# Отслеживаемые предметы
TARGET_ITEMS = {
    'octobloom': {'keywords': ['octobloom'], 'display_name': '🐙 Octobloom'},
    'zebrazinkle': {'keywords': ['zebrazinkle', 'zebra zinkle'], 'display_name': '🦓 Zebrazinkle'},
    'firework_fern': {'keywords': ['firework fern', 'fireworkfern'], 'display_name': '🎆 Firework Fern'},
    'tomato': {'keywords': ['tomato'], 'display_name': '🍅 Tomato'}
}

# ==================== ГЛОБАЛЬНЫЕ ДАННЫЕ ====================
game_data = {
    'last_stock': {},          # Последние данные по секциям
    'last_update': None,       # Время последнего обновления
    'connected': False,        # Статус подключения
    'total_updates': 0,        # Всего обновлений
    'found_items': [],         # Найденные целевые предметы
    'stock_history': []        # История изменений
}

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML"):
    try:
        import requests
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

# ==================== ОБРАБОТКА ДАННЫХ ====================
def check_for_target_items(new_stock_data):
    """Ищет целевые предметы в новых данных"""
    found_items = []
    
    # Проверяем секцию семян
    if 'SEED_STOCK' in new_stock_data:
        for seed in new_stock_data['SEED_STOCK']:
            seed_name = seed.get('display_name', '').lower()
            quantity = seed.get('quantity', 0)
            
            for item_id, config in TARGET_ITEMS.items():
                for keyword in config['keywords']:
                    if keyword in seed_name and quantity > 0:
                        found_items.append({
                            'id': item_id,
                            'name': seed_name,
                            'display_name': config['display_name'],
                            'quantity': quantity,
                            'section': 'SEED_STOCK'
                        })
    
    # Также проверяем другие секции если нужно
    sections_to_check = ['COSMETIC_STOCK', 'EGG_STOCK', 'GEAR_STOCK', 'EVENTSHOP_STOCK']
    
    for section in sections_to_check:
        if section in new_stock_data:
            for item in new_stock_data[section]:
                item_name = item.get('display_name', '').lower()
                quantity = item.get('quantity', 0)
                
                # Здесь можно добавить проверку для других категорий
    
    return found_items

def compare_stocks(old_stock, new_stock):
    """Сравнивает два состояния стока"""
    changes = []
    
    # Сравниваем каждую секцию
    all_sections = set(list(old_stock.keys()) + list(new_stock.keys()))
    
    for section in all_sections:
        old_items = old_stock.get(section, [])
        new_items = new_stock.get(section, [])
        
        # Преобразуем в словари для сравнения
        old_dict = {item.get('display_name', '').lower(): item.get('quantity', 0) for item in old_items}
        new_dict = {item.get('display_name', '').lower(): item.get('quantity', 0) for item in new_items}
        
        # Все уникальные имена
        all_names = set(list(old_dict.keys()) + list(new_dict.keys()))
        
        for name in all_names:
            old_qty = old_dict.get(name, 0)
            new_qty = new_dict.get(name, 0)
            
            if old_qty != new_qty:
                changes.append({
                    'section': section,
                    'name': name,
                    'old': old_qty,
                    'new': new_qty,
                    'change': new_qty - old_qty
                })
    
    return changes

# ==================== WEB SOCKET КЛИЕНТ ====================
async def websocket_client():
    """Подключается к новому WebSocket серверу"""
    
    logger.info(f"🔗 Подключаюсь к: {WEBSOCKET_URL}")
    
    while True:
        try:
            async with websockets.connect(
                WEBSOCKET_URL,
                ping_interval=30,
                ping_timeout=10
            ) as websocket:
                game_data['connected'] = True
                logger.info("✅ УСПЕШНОЕ ПОДКЛЮЧЕНИЕ! Жду обновлений...")
                send_to_bot("🎮 <b>Подключился к игре!</b>\nОжидаю обновлений стока...")
                
                while True:
                    try:
                        # Получаем сообщение
                        raw_message = await websocket.recv()
                        data = json.loads(raw_message)
                        timestamp = datetime.now()
                        
                        game_data['last_update'] = timestamp
                        game_data['total_updates'] += 1
                        
                        # Логируем получение
                        if game_data['total_updates'] % 10 == 0:
                            sections = list(data.keys())
                            logger.info(f"📨 Обновление #{game_data['total_updates']}. Секции: {sections}")
                        
                        # Сохраняем текущий сток
                        current_stock = {}
                        for section, items in data.items():
                            current_stock[section.upper()] = items
                        
                        # Сравниваем с предыдущим
                        if game_data['last_stock']:
                            changes = compare_stocks(game_data['last_stock'], current_stock)
                            
                            if changes:
                                logger.info(f"🎯 Найдено изменений: {len(changes)}")
                                
                                # Ищем целевые предметы
                                new_items = check_for_target_items(current_stock)
                                
                                if new_items:
                                    for item in new_items:
                                        message = (
                                            f"🎯 <b>НАЙДЕН ПРЕДМЕТ!</b>\n\n"
                                            f"{item['display_name']}\n"
                                            f"📦 Количество: {item['quantity']} шт\n"
                                            f"📂 Раздел: {item['section']}\n"
                                            f"🕒 Время: {timestamp.strftime('%H:%M:%S')}\n\n"
                                            f"⚡ Скорее в игру!"
                                        )
                                        send_to_channel(message)
                                        logger.info(f"📢 Отправлено: {item['display_name']}")
                        
                        # Обновляем последний сток
                        game_data['last_stock'] = current_stock
                        
                        # Сохраняем в историю (первые 50 записей)
                        if len(game_data['stock_history']) < 50:
                            game_data['stock_history'].append({
                                'timestamp': timestamp,
                                'data_summary': {k: len(v) for k, v in current_stock.items()}
                            })
                        
                    except json.JSONDecodeError:
                        logger.warning("⚠️ Невалидный JSON от сервера")
                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки: {e}")
                
        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK) as e:
            game_data['connected'] = False
            logger.warning(f"🔌 Соединение разорвано: {e}. Переподключение через 5 сек...")
            await asyncio.sleep(5)
            
        except Exception as e:
            game_data['connected'] = False
            logger.error(f"❌ Ошибка подключения: {e}")
            await asyncio.sleep(10)

def run_websocket():
    """Запуск WebSocket в отдельном потоке"""
    asyncio.run(websocket_client())

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    """Главная страница"""
    
    status = "🟢 ПОДКЛЮЧЕН" if game_data['connected'] else "🔴 ОТКЛЮЧЕН"
    last_update = game_data['last_update']
    update_str = last_update.strftime('%H:%M:%S') if last_update else "никогда"
    
    # Статистика по секциям
    sections_info = ""
    if game_data['last_stock']:
        for section, items in game_data['last_stock'].items():
            sections_info += f"<li><b>{section}</b>: {len(items)} предметов</li>"
    
    return f"""
    <html>
    <head><title>🎮 Прямой мониторинг (новый сервер)</title></head>
    <body style="margin:40px;font-family:Arial;">
        <h1>🎮 Прямой мониторинг Grow a Garden</h1>
        <h3>🔗 Новый WebSocket сервер</h3>
        
        <div style="background:#f0f8ff;padding:20px;border-radius:10px;">
            <h2>📡 Статус: {status}</h2>
            <p>🕒 Последнее обновление: {update_str}</p>
            <p>📨 Всего обновлений: {game_data['total_updates']}</p>
            <p>🎯 Отслеживаю: {len(TARGET_ITEMS)} предметов</p>
            <p>🔗 Сервер: websocket.joshlei.com</p>
        </div>
        
        <div style="background:#fff;padding:20px;border-radius:10px;margin-top:20px;">
            <h3>📊 Текущий сток:</h3>
            <ul>
                {sections_info if sections_info else "<li>Нет данных</li>"}
            </ul>
        </div>
        
        <div style="background:#e7f3ff;padding:20px;border-radius:10px;margin-top:20px;">
            <h3>⚡ Как работает:</h3>
            <ol>
                <li>Подключение к <b>websocket.joshlei.com</b></li>
                <li>Получение обновлений в реальном времени</li>
                <li>Поиск целевых предметов (Octobloom и др.)</li>
                <li>Уведомления в Telegram при обнаружении</li>
            </ol>
        </div>
        
        <p><a href="/stock">Посмотреть данные стока</a> | <a href="/status">Статус API</a></p>
    </body>
    </html>
    """

@app.route('/stock')
def show_stock():
    """Показывает данные стока"""
    if not game_data['last_stock']:
        return "Нет данных о стоке"
    
    stock_data = {}
    for section, items in game_data['last_stock'].items():
        stock_data[section] = []
        for item in items[:10]:  # Первые 10 предметов каждой секции
            stock_data[section].append({
                'name': item.get('display_name', 'Unknown'),
                'quantity': item.get('quantity', 0)
            })
    
    return jsonify({
        'timestamp': game_data['last_update'].isoformat() if game_data['last_update'] else None,
        'total_updates': game_data['total_updates'],
        'stock': stock_data
    })

@app.route('/status')
def status():
    """Статус системы"""
    return jsonify({
        'connected': game_data['connected'],
        'last_update': game_data['last_update'].isoformat() if game_data['last_update'] else None,
        'total_updates': game_data['total_updates'],
        'websocket_url': WEBSOCKET_URL,
        'tracking_items': list(TARGET_ITEMS.keys())
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🎮 ЗАПУСК МОНИТОРИНГА (НОВЫЙ СЕРВЕР)")
    logger.info("=" * 60)
    logger.info(f"🔗 WebSocket: {WEBSOCKET_URL}")
    logger.info("🎯 Отслеживаю: Octobloom, Zebrazinkle, Firework Fern, Tomato")
    logger.info("⚡ Режим: реальное время с нового сервера")
    logger.info("=" * 60)
    
    # Запускаем WebSocket клиент
    ws_thread = threading.Thread(target=run_websocket, daemon=True)
    ws_thread.start()
    logger.info("✅ WebSocket клиент запущен")
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
