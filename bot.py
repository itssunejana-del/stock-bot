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
    logger.info("⏸️ ⚠️ БОТ ПРИОСТАНОВЛЕН НА 3 ЧАСА")
    logger.info("Discord ограничил запросы. Ожидаю снятия ограничений...")
    
    # Спим 3 часа (10800 секунд)
    time.sleep(10800)
    
    logger.info("⏰ 3 часа прошли. Discord должен был снять ограничения.")
    logger.info("Теперь можно удалить PAUSE_BOT переменную и обновить код.")
    
    # Выходим из программы
    import sys
    sys.exit(0)

# ==================== ОСНОВНОЙ КОД ====================
@app.route('/')
def home():
    return "⚠️ Бот приостановлен через PAUSE_BOT=true. Удалите эту переменную чтобы продолжить."

if __name__ == '__main__':
    logger.info("🚨 Этот код только для паузы. Замените его на рабочий код после снятия ограничений Discord.")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
