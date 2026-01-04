from flask import Flask
import requests
import os
import time
import logging
import threading
from datetime import datetime
import json
import websocket  # ← ЭТО РАБОТАЕТ С ВАШИМИ ЗАВИСИМОСТЯМИ!
import _thread as thread

# Настройка логирования
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
game_data = {
    'seeds': {},
    'last_update': None,
    'connected': False
}

# Отслеживаемые предметы
TARGET_ITEMS = {
    'tomato': {'keywords': ['tomato'], 'display_name': '🍅 Помидор'},
    'octobloom': {'keywords': ['octobloom'], 'display_name': '🐙 Octobloom'},
    'zebrazinkle': {'keywords': ['zebrazinkle'], 'display_name': '🦓 Zebrazinkle'},
    'firework_fern': {'keywords': ['firework fern'], 'display_name': '🎆 Firework Fern'}
}

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

# ==================== WEB SOCKET (совместимый с вашими зависимостями) ====================
def on_message(ws, message):
    """Обрабатывает сообщения от WebSocket"""
    global game_data
    
    try:
        data = json.loads(message)
        
        if data.get('type') and 'data' in data:
            # Получаем семена
            new_seeds = {}
            for seed in data['data'].get('seeds', []):
                name = seed.get('name', '').lower()
                quantity = seed.get('quantity', 0)
                if name:
                    new_seeds[name] = quantity
            
            # Проверяем изменения
            old_seeds = game_data['seeds']
            changes = []
            
            for item_name, config in TARGET_ITEMS.items():
                for keyword in config['keywords']:
                    for seed_name, quantity in new_seeds.items():
                        if keyword in seed_name:
                            old_qty = old_seeds.get(seed_name, 0)
                            if old_qty != quantity:
                                changes.append({
                                    'name': seed_name,
                                    'display_name': config['display_name'],
                                    'old': old_qty,
                                    'new': quantity
                                })
            
            # Обновляем данные
            game_data['seeds'] = new_seeds
            game_data['last_update'] = datetime.now()
            
            # Отправляем уведомления
            if changes:
                for change in changes:
                    if change['old'] == 0 and change['new'] > 0:
                        message_text = f"🎯 <b>{change['display_name']} ПОЯВИЛСЯ!</b>\n📦 Количество: {change['new']} шт"
                    elif change['new'] > change['old']:
                        message_text = f"📈 <b>{change['display_name']}</b>\n➕ Добавилось: {change['new'] - change['old']} шт"
                    else:
                        message_text = f"📉 <b>{change['display_name']}</b>\n➖ Убавилось: {change['old'] - change['new']} шт"
                    
                    send_to_channel(message_text)
                    logger.info(f"📢 {change['display_name']}: {change['old']} → {change['new']}")
                    
    except json.JSONDecodeError:
        logger.warning("⚠️ Не удалось распарсить сообщение")
    except Exception as e:
        logger.error(f"❌ Ошибка обработки: {e}")

def on_error(ws, error):
    logger.error(f"❌ WebSocket ошибка: {error}")

def on_close(ws, close_status_code, close_msg):
    logger.warning(f"🔌 WebSocket закрыт: {close_status_code} - {close_msg}")
    game_data['connected'] = False
    # Переподключение через 5 секунд
    time.sleep(5)
    connect_websocket()

def on_open(ws):
    logger.info("✅ WebSocket подключен к игре!")
    game_data['connected'] = True
    send_to_bot("🎮 <b>Подключился к игре!</b>\nНачинаю мониторинг в реальном времени.")

def connect_websocket():
    """Подключается к WebSocket игры"""
    websocket_url = "wss://ws.growagardenpro.com/"
    
    logger.info(f"🔗 Подключаюсь к: {websocket_url}")
    
    ws = websocket.WebSocketApp(
        websocket_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    
    ws.run_forever()

# ==================== МОНИТОРИНГ ====================
def monitor_websocket():
    """Запускает WebSocket в отдельном потоке"""
    while True:
        try:
            connect_websocket()
        except Exception as e:
            logger.error(f"💥 Критическая ошибка WebSocket: {e}")
            time.sleep(10)

def monitor_status():
    """Мониторит статус и отправляет периодические отчеты"""
    while True:
        try:
            # Логируем статус
            if game_data['connected']:
                tomatoes = game_data['seeds'].get('tomato', 0)
                logger.info(f"📡 Онлайн. Помидоров: {tomatoes} шт")
            else:
                logger.warning("📡 Оффлайн. Переподключение...")
            
            time.sleep(300)  # Каждые 5 минут
            
        except Exception as e:
            logger.error(f"❌ Ошибка в мониторе: {e}")
            time.sleep(60)

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    tomatoes = game_data['seeds'].get('tomato', 0)
    
    status = "🟢 ПОДКЛЮЧЕНО" if game_data['connected'] else "🔴 ОТКЛЮЧЕНО"
    
    seeds_list = []
    for name, qty in sorted(game_data['seeds'].items()):
        seeds_list.append(f"{name}: {qty} шт")
    
    return f"""
    <html>
    <head><title>🎮 Мониторинг игры</title><meta charset="utf-8"></head>
    <body style="margin:40px;font-family:Arial;">
        <h1>🎮 Прямой мониторинг Grow a Garden</h1>
        
        <div style="background:#f0f8ff;padding:20px;border-radius:10px;margin:20px 0;">
            <h2>📡 Статус: {status}</h2>
            <p>🍅 Помидоров: {tomatoes} шт</p>
            <p>🔄 Обновляется в реальном времени</p>
        </div>
        
        <div style="background:#fff;padding:20px;border-radius:10px;margin:20px 0;">
            <h3>📊 Все семена ({len(game_data['seeds'])}):</h3>
            <pre>{'\\n'.join(seeds_list) if seeds_list else 'Нет данных'}</pre>
        </div>
    </body>
    </html>
    """

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🎮 ЗАПУСК ПРЯМОГО ПОДКЛЮЧЕНИЯ К ИГРЕ")
    logger.info("=" * 60)
    
    # Запускаем WebSocket в отдельном потоке
    ws_thread = threading.Thread(target=monitor_websocket, daemon=True)
    ws_thread.start()
    logger.info("✅ WebSocket поток запущен")
    
    # Запускаем монитор статуса
    status_thread = threading.Thread(target=monitor_status, daemon=True)
    status_thread.start()
    logger.info("✅ Монитор статуса запущен")
    
    # Отправляем сообщение о запуске
    startup_msg = (
        "🎮 <b>ПРЯМОЕ ПОДКЛЮЧЕНИЕ ЗАПУЩЕНО!</b>\n\n"
        "⚡ <b>Новый режим:</b> WebSocket прямо к игре\n"
        "🎯 <b>Отслеживаю:</b> помидоры + редкие семена\n"
        "✅ <b>Уведомления при изменении количества</b>"
    )
    send_to_bot(startup_msg)
    
    # Запускаем Flask
    port = int(os.getenv('PORT', 10000))
    logger.info(f"🌐 Веб-сервер на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
