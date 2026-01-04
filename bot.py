from flask import Flask
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

# ==================== ВАШ DISCORD ID ЗДЕСЬ ====================
# ↓↓↓ ВСТАВЬТЕ ВАШ ID МЕЖДУ КАВЫЧЕК ↓↓↓
YOUR_DISCORD_ID = "350951361753513985"
# ↑↑↑ ВСТАВЬТЕ ВАШ ID МЕЖДУ КАВЫЧЕК ↑↑↑

WEBSOCKET_URL = f"wss://websocket.joshlei.com/growagarden?user_id={YOUR_DISCORD_ID}"

# ==================== ОСТАЛЬНОЙ КОД ====================
game_data = {
    'last_stock': {},
    'last_update': None,
    'connected': False,
    'total_updates': 0
}

async def websocket_client():
    """Подключается к WebSocket с вашим ID"""
    
    logger.info(f"🔗 Подключаюсь с ID: {YOUR_DISCORD_ID}")
    
    while True:
        try:
            async with websockets.connect(WEBSOCKET_URL, timeout=10) as ws:
                game_data['connected'] = True
                logger.info("✅ ПОДКЛЮЧЕНИЕ УСПЕШНО! Жду данные...")
                
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    game_data['last_update'] = datetime.now()
                    game_data['total_updates'] += 1
                    game_data['last_stock'] = data
                    
                    # Логируем каждое обновление
                    sections = list(data.keys())
                    logger.info(f"📨 Обновление #{game_data['total_updates']}: {sections}")
                    
                    # Если есть семена - показываем
                    if 'SEED_STOCK' in data:
                        seeds = data['SEED_STOCK']
                        tomato_count = 0
                        for seed in seeds:
                            if 'tomato' in seed.get('display_name', '').lower():
                                tomato_count = seed.get('quantity', 0)
                                break
                        logger.info(f"🍅 Помидоров: {tomato_count} шт, всего семян: {len(seeds)}")
                
        except Exception as e:
            game_data['connected'] = False
            logger.error(f"❌ Ошибка: {e}")
            await asyncio.sleep(5)

def run_websocket():
    asyncio.run(websocket_client())

@app.route('/')
def home():
    status = "🟢 ПОДКЛЮЧЕН" if game_data['connected'] else "🔴 ОТКЛЮЧЕН"
    
    return f"""
    <html><body style="margin:40px;font-family:Arial;">
        <h1>🎮 Тест WebSocket с вашим ID</h1>
        <p>Статус: {status}</p>
        <p>Обновлений: {game_data['total_updates']}</p>
        <p>Последнее: {game_data['last_update'].strftime('%H:%M:%S') if game_data['last_update'] else 'нет'}</p>
        <p>ID: {YOUR_DISCORD_ID[:10]}... (первые 10 символов)</p>
    </body></html>
    """

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🎮 ТЕСТ С ВАШИМ DISCORD ID")
    logger.info("=" * 60)
    
    ws_thread = threading.Thread(target=run_websocket, daemon=True)
    ws_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
