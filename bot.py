from flask import Flask, jsonify
import asyncio
import websockets
import json
import threading
import time
from datetime import datetime
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== ГЛОБАЛЬНЫЕ ДАННЫЕ ====================
game_data = {
    'all_messages': [],           # ВСЕ сообщения
    'message_types': {},          # Статистика по типам
    'last_update': None,
    'connected': False,
    'total_received': 0,
    'last_stock_data': None,      # Последние данные стока
    'last_weather_data': None,    # Последние данные погоды
    'collection_start': datetime.now()
}

# ==================== WEB SOCKET КЛИЕНТ ====================
async def websocket_client():
    """Собирает ВСЕ данные из игры"""
    uri = "wss://ws.growagardenpro.com/"
    
    logger.info(f"🎮 Подключаюсь к игре: {uri}")
    
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                game_data['connected'] = True
                logger.info("✅ ПОДКЛЮЧЕН! Начинаю сбор ВСЕХ данных...")
                
                async for message in websocket:
                    try:
                        timestamp = datetime.now()
                        raw_message = message
                        
                        # Сохраняем сырое сообщение
                        game_data['total_received'] += 1
                        game_data['last_update'] = timestamp
                        
                        # Парсим JSON
                        try:
                            data = json.loads(raw_message)
                            msg_type = data.get('type', 'unknown')
                            
                            # Обновляем статистику
                            game_data['message_types'][msg_type] = game_data['message_types'].get(msg_type, 0) + 1
                            
                            # Сохраняем полные данные
                            message_record = {
                                'timestamp': timestamp.isoformat(),
                                'type': msg_type,
                                'data': data,
                                'raw_length': len(raw_message)
                            }
                            game_data['all_messages'].append(message_record)
                            
                            # Сохраняем последние данные по категориям
                            if msg_type == 'stock_update' and 'data' in data:
                                game_data['last_stock_data'] = {
                                    'timestamp': timestamp,
                                    'data': data['data']
                                }
                                logger.info(f"📦 Stock update: {len(data['data'].get('seeds', []))} семян")
                                
                            elif msg_type == 'weather_update' and 'data' in data:
                                game_data['last_weather_data'] = {
                                    'timestamp': timestamp,
                                    'data': data['data']
                                }
                                logger.info(f"🌤️ Weather update: {data['data'].get('type', 'unknown')}")
                            
                            # Логируем каждые 10 сообщений
                            if game_data['total_received'] % 10 == 0:
                                logger.info(f"📨 Сообщений: {game_data['total_received']}, "
                                          f"Типы: {dict(sorted(game_data['message_types'].items()))}")
                                
                        except json.JSONDecodeError:
                            logger.warning(f"⚠️ Невалидный JSON ({len(raw_message)} chars)")
                            game_data['all_messages'].append({
                                'timestamp': timestamp.isoformat(),
                                'type': 'invalid_json',
                                'raw': raw_message[:200] + '...' if len(raw_message) > 200 else raw_message
                            })
                            
                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки сообщения: {e}")
                
        except websockets.exceptions.ConnectionClosed:
            game_data['connected'] = False
            logger.warning("🔌 Соединение разорвано. Переподключение через 5 сек...")
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
    """Главная страница - показывает ВСЕ собранные данные"""
    
    status = "🟢 ПОДКЛЮЧЕН" if game_data['connected'] else "🔴 ОТКЛЮЧЕН"
    
    uptime = datetime.now() - game_data['collection_start']
    uptime_str = str(uptime).split('.')[0]
    
    # Статистика
    total_messages = game_data['total_received']
    message_types = game_data['message_types']
    
    # Примеры последних сообщений
    recent_messages = game_data['all_messages'][-5:] if game_data['all_messages'] else []
    
    # Данные стока если есть
    stock_info = ""
    if game_data['last_stock_data']:
        stock = game_data['last_stock_data']['data']
        categories = ['seeds', 'cosmetics', 'eggs', 'gear', 'honey', 'events']
        stock_info = "<h3>📊 Последний сток:</h3>"
        for cat in categories:
            if cat in stock:
                stock_info += f"<p><b>{cat}:</b> {len(stock[cat])} предметов</p>"
    
    return f"""
    <html>
    <head>
        <title>🎮 Сбор ВСЕХ данных игры</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial; margin: 40px; }}
            .card {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .message {{ background: white; padding: 10px; margin: 5px 0; border-left: 4px solid #4CAF50; }}
        </style>
    </head>
    <body>
        <h1>🎮 Сбор ВСЕХ данных из Grow a Garden</h1>
        
        <div class="card">
            <h2>📡 Статус: {status}</h2>
            <p>⏰ Сбор данных: {uptime_str}</p>
            <p>📨 Всего сообщений: {total_messages}</p>
            <p>🔄 WebSocket: wss://ws.growagardenpro.com/</p>
            <p>🕒 Последнее обновление: {game_data['last_update'].strftime('%H:%M:%S') if game_data['last_update'] else 'никогда'}</p>
        </div>
        
        <div class="card">
            <h2>📊 Статистика сообщений:</h2>
            <ul>
                {"".join([f'<li><b>{typ}</b>: {cnt} раз</li>' for typ, cnt in sorted(message_types.items())])}
            </ul>
        </div>
        
        {stock_info}
        
        <div class="card">
            <h2>📝 Последние сообщения:</h2>
            {"".join([f'<div class="message"><b>{msg["type"]}</b> ({msg["timestamp"][11:19]})</div>' for msg in recent_messages]) if recent_messages else '<p>Нет сообщений</p>'}
        </div>
        
        <div class="card">
            <h2>🔧 API эндпоинты:</h2>
            <ul>
                <li><a href="/stats">/stats</a> - Статистика</li>
                <li><a href="/messages">/messages</a> - Все сообщения (JSON)</li>
                <li><a href="/stock">/stock</a> - Последний сток</li>
                <li><a href="/types">/types</a> - Типы сообщений</li>
            </ul>
        </div>
    </body>
    </html>
    """

@app.route('/stats')
def stats():
    """Статистика в JSON"""
    uptime = datetime.now() - game_data['collection_start']
    
    return jsonify({
        'connected': game_data['connected'],
        'total_messages': game_data['total_received'],
        'message_types': game_data['message_types'],
        'uptime_seconds': uptime.total_seconds(),
        'collection_start': game_data['collection_start'].isoformat(),
        'last_update': game_data['last_update'].isoformat() if game_data['last_update'] else None,
        'websocket_url': 'wss://ws.growagardenpro.com/'
    })

@app.route('/messages')
def messages():
    """Все сообщения (первые 100)"""
    return jsonify({
        'total': len(game_data['all_messages']),
        'sample': game_data['all_messages'][:100]
    })

@app.route('/stock')
def stock():
    """Последние данные стока"""
    if game_data['last_stock_data']:
        return jsonify(game_data['last_stock_data'])
    return jsonify({'error': 'No stock data yet'})

@app.route('/types')
def types():
    """Анализ типов сообщений"""
    return jsonify({
        'types': game_data['message_types'],
        'total_types': len(game_data['message_types'])
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🎮 ЗАПУСК СБОРА ВСЕХ ДАННЫХ ИЗ ИГРЫ")
    logger.info("=" * 60)
    logger.info("🔗 WebSocket: wss://ws.growagardenpro.com/")
    logger.info("🎯 Цель: собрать ВСЕ типы данных для анализа")
    logger.info("📊 Режим: полный сбор + веб-интерфейс")
    logger.info("=" * 60)
    
    # Запускаем WebSocket клиент
    ws_thread = threading.Thread(target=run_websocket, daemon=True)
    ws_thread.start()
    logger.info("✅ WebSocket клиент запущен")
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер запускается на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
