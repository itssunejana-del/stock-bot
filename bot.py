from flask import Flask
import os
import time
import logging

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Проверка переменной паузы
PAUSE_BOT = os.getenv('PAUSE_BOT', 'false').lower() == 'true'

@app.route('/')
def home():
    if PAUSE_BOT:
        return """
        <h1>⏸️ Бот приостановлен</h1>
        <p>Discord ограничил запросы. Ожидаю снятия ограничений.</p>
        <p><strong>Не удаляйте эту страницу и переменную PAUSE_BOT.</strong></p>
        """
    else:
        return "⚠️ Переменная PAUSE_BOT не установлена в 'true'."

if __name__ == '__main__':
    if PAUSE_BOT:
        logger.info("⏸️ Бот приостановлен на 4 часа (14400 секунд). Discord должен снять ограничения.")
    else:
        logger.warning("⚠️ PAUSE_BOT не равен 'true'. Бот будет работать в обычном режиме.")
    
    # ОБЯЗАТЕЛЬНО: Преобразовать строку PORT в число [citation:7]
    port = int(os.environ.get('PORT', 10000))
    # КРИТИЧНО: Запускать сервер на 0.0.0.0 [citation:2][citation:9][citation:10]
    app.run(host='0.0.0.0', port=port, debug=False)
