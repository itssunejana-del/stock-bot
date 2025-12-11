from flask import Flask
import os
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== ЭКСТРЕННАЯ ПАУЗА ====================
PAUSE_BOT = os.getenv('PAUSE_BOT', 'false').lower() == 'true'

if PAUSE_BOT:
    logger.info("⏸️ ⚠️ БОТ ПРИОСТАНОВЛЕН НА 4 ЧАСА (14400 секунд)")
    logger.info("Discord ограничил запросы. Ожидаю снятия ограничений...")
    
    # Спим 4 часа
    time.sleep(14400)
    
    logger.info("⏰ 4 часа прошли. Discord должен был снять ограничения.")
    exit(0)

@app.route('/')
def home():
    return "⚠️ Бот приостановлен через PAUSE_BOT=true"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
