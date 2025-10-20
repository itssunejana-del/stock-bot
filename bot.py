from flask import Flask
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    logger.info("✅ Кто-то зашел на главную страницу!")
    return "🎯 Бот работает! Если видишь это - Flask запущен."

@app.route('/test')
def test():
    logger.info("✅ Тестовая страница вызвана!")
    return "Тест пройден! Логи должны появиться."

if __name__ == '__main__':
    logger.info("🚀 ПРИЛОЖЕНИЕ ЗАПУЩЕНО!")
    print("=== ЭТО ДОЛЖНО БЫТЬ В ЛОГАХ ===")
    app.run(host='0.0.0.0', port=5000, debug=True)
