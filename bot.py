from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <h1>🚫 WebSocket требует авторизации</h1>
    <p>Сервер websocket.joshlei.com требует токен.</p>
    <p>Нужно искать другой источник данных.</p>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
