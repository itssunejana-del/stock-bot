from flask import Flask, jsonify
import asyncio
import websockets
import json
import threading
import time
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== ГЛОБАЛЬНЫЕ ДАННЫЕ ====================
game_data = {
    'seeds': [],
    'last_update': None,
    'connected': False,
    'total_messages': 0
}

# ==================== WEB SOCKET КЛИЕНТ ====================
async def websocket_client():
    """Прямое подключение к игре"""
    uri = "wss://ws.growagardenpro.com/"
    
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                game_data['connected'] = True
                logger.info("✅ ПОДКЛЮЧЕН К ИГРЕ! Получаю данные...")
                
                async for message in websocket:
                    try:
                        game_data['total_messages'] += 1
                        data = json.loads(message)
                        
                        # Сохраняем время последнего обновления
                        game_data['last_update'] = datetime.now()
                        
                        # Если это обновление стока
                        if data.get('type') == 'stock_update' and 'data' in data:
                            stock_data = data['data']
                            
                            # Сохраняем семена
                            if 'seeds' in stock_data:
                                game_data['seeds'] = stock_data['seeds']
                                logger.info(f"📦 Получены {len(stock_data['seeds'])} семян")
                            
                            # Логируем что есть
                            if game_data['total_messages'] % 10 == 0:  # Каждое 10-е сообщение
                                seed_names = [s.get('name', '') for s in game_data['seeds'][:3]]
                                logger.info(f"📊 Семена: {', '.join(seed_names)}...")
                                
                    except json.JSONDecodeError:
                        logger.warning("⚠️ Невалидный JSON от игры")
                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки: {e}")
                
        except websockets.exceptions.ConnectionClosed:
            game_data['connected'] = False
            logger.warning("🔌 Соединение разорвано. Переподключение...")
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
    status = "🟢 ПОДКЛЮЧЕН" if game_data['connected'] else "🔴 ОТКЛЮЧЕН"
    
    last_update = game_data['last_update']
    update_str = last_update.strftime('%H:%M:%S') if last_update else "никогда"
    
    # Примеры семян
    sample_seeds = []
    for seed in game_data['seeds'][:10]:  # Первые 10 семян
        name = seed.get('name', 'Unknown')
        quantity = seed.get('quantity', 0)
        sample_seeds.append(f"{name}: {quantity} шт")
    
    return f"""
    <html>
    <head><title>🎮 Прямое подключение к игре</title></head>
    <body style="margin:40px;font-family:Arial;">
        <h1>🎮 Прямое подключение к Grow a Garden</h1>
        
        <div style="background:#f0f8ff;padding:20px;border-radius:10px;">
            <h2>📡 Статус: {status}</h2>
            <p>🕒 Последнее обновление: {update_str}</p>
            <p>📨 Получено сообщений: {game_data['total_messages']}</p>
            <p>🌱 Семян получено: {len(game_data['seeds'])} видов</p>
            <p>🔗 WebSocket: wss://ws.growagardenpro.com/</p>
        </div>
        
        <div style="background:#fff;padding:20px;border-radius:10px;margin-top:20px;">
            <h3>📊 Последние семена:</h3>
            <ul>
                {''.join([f'<li>{seed}</li>' for seed in sample_seeds]) if sample_seeds else '<li>Нет данных</li>'}
            </ul>
        </div>
        
        <div style="background:#e7f3ff;padding:20px;border-radius:10px;margin-top:20px;">
            <h3>⚡ Как работает:</h3>
            <ol>
                <li>Прямое подключение к серверу игры</li>
                <li>Получает данные в РЕАЛЬНОМ ВРЕМЕНИ</li>
                <li>НИКАКИХ посредников (Discord/API)</li>
                <li>Данные обновляются мгновенно</li>
            </ol>
        </div>
    </body>
    </html>
    """

@app.route('/data')
def get_data():
    """API для получения данных"""
    return jsonify({
        'connected': game_data['connected'],
        'last_update': game_data['last_update'].isoformat() if game_data['last_update'] else None,
        'total_messages': game_data['total_messages'],
        'seeds_count': len(game_data['seeds']),
        'seeds': game_data['seeds'][:20]  # Первые 20 семян
    })

@app.route('/check')
def check_connection():
    """Проверка соединения"""
    return jsonify({
        'websocket_connected': game_data['connected'],
        'alive': True,
        'timestamp': datetime.now().isoformat()
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🎮 ЗАПУСК ПРЯМОГО ПОДКЛЮЧЕНИЯ К ИГРЕ")
    logger.info("=" * 60)
    logger.info("🔗 WebSocket: wss://ws.growagardenpro.com/")
    logger.info("⚡ Режим: реальное время (WebSocket)")
    logger.info("🎯 Источник: напрямую от сервера игры")
    logger.info("=" * 60)
    
    # Запускаем WebSocket клиент в отдельном потоке
    ws_thread = threading.Thread(target=run_websocket, daemon=True)
    ws_thread.start()
    logger.info("✅ WebSocket клиент запущен")
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
