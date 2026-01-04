from flask import Flask, request, jsonify
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
import json
import asyncio
import websockets

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
# Хранилище данных из игры
game_data = {
    'seeds': {},
    'last_update': None,
    'connected': False
}

# Отслеживаемые предметы
TARGET_ITEMS = {
    'tomato': {
        'keywords': ['tomato'],
        'display_name': '🍅 Помидор',
        'emoji': '🍅'
    },
    'octobloom': {
        'keywords': ['octobloom'],
        'display_name': '🐙 Octobloom',
        'emoji': '🐙'
    },
    'zebrazinkle': {
        'keywords': ['zebrazinkle'],
        'display_name': '🦓 Zebrazinkle',
        'emoji': '🦓'
    },
    'firework_fern': {
        'keywords': ['firework fern'],
        'display_name': '🎆 Firework Fern',
        'emoji': '🎆'
    }
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

# ==================== WEB SOCKET ПОДКЛЮЧЕНИЕ ====================
async def connect_to_game():
    """Подключается к игре через WebSocket"""
    global game_data
    
    websocket_url = "wss://ws.growagardenpro.com/"
    
    logger.info(f"🔗 Пытаюсь подключиться к игре: {websocket_url}")
    
    while True:
        try:
            async with websockets.connect(websocket_url) as websocket:
                game_data['connected'] = True
                logger.info("✅ Успешное подключение к игре!")
                send_to_bot("🎮 <b>Подключился к игре!</b>\nНачинаю получать данные в реальном времени.")
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        
                        if data.get('type') and 'data' in data:
                            # Обновляем данные
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
                                    # Ищем все семена с этим ключевым словом
                                    for seed_name, quantity in new_seeds.items():
                                        if keyword in seed_name:
                                            old_qty = old_seeds.get(seed_name, 0)
                                            if old_qty != quantity:
                                                changes.append({
                                                    'name': seed_name,
                                                    'display_name': config['display_name'],
                                                    'emoji': config['emoji'],
                                                    'old': old_qty,
                                                    'new': quantity
                                                })
                            
                            # Обновляем хранилище
                            game_data['seeds'] = new_seeds
                            game_data['last_update'] = datetime.now()
                            
                            # Отправляем уведомления об изменениях
                            if changes:
                                for change in changes:
                                    message_text = (
                                        f"{change['emoji']} <b>{change['display_name']}</b>\n"
                                        f"📦 Было: {change['old']} шт\n"
                                        f"📦 Стало: <b>{change['new']} шт</b>\n"
                                        f"🕒 {datetime.now().strftime('%H:%M:%S')}"
                                    )
                                    send_to_channel(message_text)
                                    logger.info(f"📢 {change['display_name']}: {change['old']} → {change['new']}")
                            
                    except json.JSONDecodeError:
                        logger.warning("⚠️ Не удалось распарсить сообщение от игры")
                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки: {e}")
                
        except websockets.exceptions.ConnectionClosed:
            game_data['connected'] = False
            logger.warning("🔌 Соединение разорвано. Переподключение через 5 секунд...")
            await asyncio.sleep(5)
        except Exception as e:
            game_data['connected'] = False
            logger.error(f"❌ Ошибка подключения: {e}")
            logger.info("🔄 Переподключение через 10 секунд...")
            await asyncio.sleep(10)

def start_websocket():
    """Запускает WebSocket в отдельном потоке"""
    asyncio.run(connect_to_game())

# ==================== МОНИТОРИНГ СТАТУСА ====================
def monitor_status():
    """Мониторит статус подключения"""
    while True:
        try:
            if not game_data['connected']:
                status = "🔴 Нет подключения"
            else:
                last_update = game_data['last_update']
                if last_update:
                    sec_ago = (datetime.now() - last_update).total_seconds()
                    status = f"🟢 Онлайн (данные {sec_ago:.0f} сек назад)"
                else:
                    status = "🟡 Подключено, данных ещё нет"
            
            # Логируем статус каждые 5 минут
            logger.info(f"📡 Статус: {status}")
            
            # Отправляем статус раз в 30 минут
            current_time = datetime.now()
            if not hasattr(monitor_status, 'last_status_sent'):
                monitor_status.last_status_sent = current_time
            
            if (current_time - monitor_status.last_status_sent).total_seconds() > 1800:  # 30 минут
                tomatoes = game_data['seeds'].get('tomato', 0)
                status_msg = (
                    f"📊 <b>Статус мониторинга</b>\n\n"
                    f"{status}\n"
                    f"🍅 Помидоров: {tomatoes} шт\n"
                    f"⏰ Работает: {(current_time - bot_start_time).total_seconds()/3600:.1f} ч\n"
                    f"🔄 Обновляется в реальном времени"
                )
                send_to_bot(status_msg)
                monitor_status.last_status_sent = current_time
            
            time.sleep(300)  # Проверка каждые 5 минут
            
        except Exception as e:
            logger.error(f"❌ Ошибка в мониторе статуса: {e}")
            time.sleep(60)

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    tomatoes = game_data['seeds'].get('tomato', 0)
    last_update = game_data['last_update']
    
    if last_update:
        update_str = last_update.strftime('%H:%M:%S')
        sec_ago = (datetime.now() - last_update).total_seconds()
    else:
        update_str = "никогда"
        sec_ago = 0
    
    # Текущие семена
    seeds_list = []
    for name, qty in sorted(game_data['seeds'].items()):
        seeds_list.append(f"{name}: {qty} шт")
    
    return f"""
    <html>
    <head>
        <title>🎮 Прямой мониторинг игры</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f0f8ff; }}
            .card {{ background: white; padding: 20px; border-radius: 10px; margin: 20px 0; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            .online {{ color: green; font-weight: bold; }}
            .offline {{ color: red; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>🎮 Прямой мониторинг Grow a Garden</h1>
        
        <div class="card">
            <h2>📡 Статус подключения</h2>
            <p>Подключение: <span class="{'online' if game_data['connected'] else 'offline'}">
                {'🟢 ПОДКЛЮЧЕНО' if game_data['connected'] else '🔴 ОТКЛЮЧЕНО'}
            </span></p>
            <p>Последнее обновление: {update_str} ({sec_ago:.0f} сек назад)</p>
            <p>Запущен: {bot_start_time.strftime('%d.%m.%Y %H:%M')}</p>
        </div>
        
        <div class="card">
            <h2>🎯 Отслеживаемые предметы</h2>
            <ul>
                <li>🍅 Помидор (Tomato): {tomatoes} шт</li>
                <li>🐙 Octobloom</li>
                <li>🦓 Zebrazinkle</li>
                <li>🎆 Firework Fern</li>
            </ul>
        </div>
        
        <div class="card">
            <h2>📊 Все семена в игре ({len(game_data['seeds'])} видов)</h2>
            <pre>{'\\n'.join(seeds_list) if seeds_list else 'Нет данных'}</pre>
        </div>
        
        <div class="card">
            <h2>⚡ Как работает</h2>
            <ol>
                <li>Прямое подключение к игре через WebSocket</li>
                <li>Данные приходят в реальном времени</li>
                <li>Уведомления в Telegram при изменении количества</li>
                <li>Без посредников (Discord/API)</li>
            </ol>
        </div>
    </body>
    </html>
    """

@app.route('/status')
def status_api():
    """API статуса"""
    return jsonify({
        'connected': game_data['connected'],
        'last_update': game_data['last_update'].isoformat() if game_data['last_update'] else None,
        'seeds_count': len(game_data['seeds']),
        'tomatoes': game_data['seeds'].get('tomato', 0),
        'uptime': (datetime.now() - bot_start_time).total_seconds()
    })

@app.route('/seeds')
def seeds_api():
    """API списка семян"""
    return jsonify(game_data['seeds'])

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🎮 ЗАПУСК ПРЯМОГО МОНИТОРИНГА ИГРЫ")
    logger.info("=" * 60)
    logger.info("🔗 WebSocket: wss://ws.growagardenpro.com/")
    logger.info("🎯 Отслеживаю: помидоры + 3 редких семени")
    logger.info("⚡ Режим: реальное время (без задержек)")
    logger.info("=" * 60)
    
    # Запускаем WebSocket в отдельном потоке
    ws_thread = threading.Thread(target=start_websocket, daemon=True)
    ws_thread.start()
    logger.info("✅ Поток WebSocket запущен")
    
    # Запускаем монитор статуса
    status_thread = threading.Thread(target=monitor_status, daemon=True)
    status_thread.start()
    logger.info("✅ Монитор статуса запущен")
    
    # Отправляем сообщение о запуске
    startup_msg = (
        "🎮 <b>ПРЯМОЙ МОНИТОРИНГ ИГРЫ ЗАПУЩЕН!</b>\n\n"
        "⚡ <b>Новый режим работы:</b>\n"
        "• Прямое подключение к игре\n"
        "• Данные в реальном времени\n"
        "• Без посредников (Discord/API)\n\n"
        "🎯 <b>Отслеживаю:</b>\n"
        "🍅 Помидоры (для теста)\n"
        "🐙 Octobloom\n"
        "🦓 Zebrazinkle\n" 
        "🎆 Firework Fern\n\n"
        "✅ <b>Когда предмет появится/изменится</b> - вы получите уведомление!"
    )
    send_to_bot(startup_msg)
    
    # Запускаем Flask
    port = int(os.getenv('PORT', 10000))
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
