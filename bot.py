from flask import Flask
import requests
import os
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Токены
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Статус
startup_time = datetime.now()
discord_status = "⏳ Проверяю..."
telegram_sent = False

def send_telegram(text):
    """Отправка в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_BOT_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False

def check_discord():
    """Проверка Discord соединения"""
    global discord_status
    
    if not DISCORD_TOKEN:
        discord_status = "❌ Нет токена Discord"
        return False
    
    try:
        logger.info("🔍 Проверяю Discord...")
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        # Делаем запрос
        response = requests.get(
            "https://discord.com/api/v10/users/@me",
            headers=headers,
            timeout=20
        )
        
        logger.info(f"📊 Discord ответ: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            bot_name = data.get('username', 'Unknown')
            discord_status = f"✅ Бот: {bot_name}"
            return True
        elif response.status_code == 401:
            discord_status = "❌ Неверный токен"
            return False
        elif response.status_code == 403:
            discord_status = "❌ Нет доступа"
            return False
        elif response.status_code == 429:
            retry_after = 60
            try:
                retry_data = response.json()
                retry_after = retry_data.get('retry_after', 60)
            except:
                pass
            discord_status = f"⚠️ Rate limit (ждем {retry_after}сек)"
            time.sleep(retry_after)
            return False
        else:
            discord_status = f"❌ Ошибка: {response.status_code}"
            return False
            
    except requests.exceptions.Timeout:
        discord_status = "⏱️ Таймаут"
        return False
    except requests.exceptions.ConnectionError:
        discord_status = "🔌 Ошибка соединения"
        return False
    except Exception as e:
        discord_status = f"💥 Ошибка: {str(e)[:50]}"
        return False

def check_channels():
    """Проверка каналов"""
    if not DISCORD_TOKEN:
        return "❌ Нет токена"
    
    channels = ['917417', '381036', '446956']
    results = []
    
    for channel_id in channels:
        try:
            url = f"https://discord.com/api/v10/channels/{channel_id}"
            headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                results.append(f"✅ {channel_id}")
            elif response.status_code == 404:
                results.append(f"❌ {channel_id} (не найден)")
            elif response.status_code == 403:
                results.append(f"🚫 {channel_id} (нет доступа)")
            else:
                results.append(f"⚠️ {channel_id} ({response.status_code})")
                
            time.sleep(1)  # Пауза между проверками
            
        except Exception as e:
            results.append(f"💥 {channel_id} (ошибка)")
    
    return "\n".join(results)

@app.route('/')
def home():
    """Главная страница"""
    global telegram_sent
    
    # При первом заходе проверяем Discord и отправляем отчет
    if not telegram_sent:
        # Проверяем Discord
        discord_ok = check_discord()
        
        # Проверяем каналы
        channels_status = check_channels()
        
        # Отправляем в Telegram
        message = (
            f"🌐 <b>СТАТУС БОТА</b>\n\n"
            f"📅 Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"🚀 Запущен: {startup_time.strftime('%H:%M:%S')}\n"
            f"🤖 Discord: {discord_status}\n\n"
            f"📡 <b>Каналы:</b>\n{channels_status}\n\n"
            f"🌍 <b>Страница:</b> https://stock-bot-cj4s.onrender.com"
        )
        
        send_telegram(message)
        telegram_sent = True
    
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    return f"""
    <html>
        <head>
            <title>🌱 Discord Bot Status</title>
            <meta http-equiv="refresh" content="30">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                .status-box {{ 
                    background: #f8f9fa; 
                    padding: 20px; 
                    border-radius: 10px;
                    border-left: 5px solid #4CAF50;
                    margin-bottom: 20px;
                }}
                .channel-box {{ 
                    background: #e3f2fd; 
                    padding: 15px; 
                    border-radius: 8px;
                    font-family: monospace;
                }}
                .good {{ color: #2e7d32; font-weight: bold; }}
                .bad {{ color: #c62828; }}
                .warning {{ color: #f57c00; }}
            </style>
        </head>
        <body>
            <h1>🌱 Discord Bot Monitor</h1>
            
            <div class="status-box">
                <h2>📊 Статус системы</h2>
                <p><strong>Discord:</strong> <span class="{'good' if '✅' in discord_status else 'bad'}">{discord_status}</span></p>
                <p><strong>Запущен:</strong> {startup_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>Время работы:</strong> {hours:.2f} часов</p>
                <p><strong>Telegram отчет:</strong> {'✅ Отправлен' if telegram_sent else '⏳ Ожидает'}</p>
            </div>
            
            <div>
                <h2>📡 Проверка каналов</h2>
                <div class="channel-box">
                    {check_channels().replace('\n', '<br>')}
                </div>
            </div>
            
            <div style="margin-top: 30px; padding: 15px; background: #fff3e0; border-radius: 8px;">
                <h3>🔄 Что делать дальше?</h3>
                <ol>
                    <li>Если Discord работает ✅ - бот начнет мониторинг автоматически</li>
                    <li>Если ошибка ❌ - проверьте токен в настройках Render</li>
                    <li>Страница обновляется каждые 30 секунд</li>
                    <li>Отчет придет в Telegram</li>
                </ol>
                <p><a href="/" style="color: #2196F3; text-decoration: none;">🔄 Обновить страницу</a></p>
            </div>
            
            <div style="margin-top: 20px; font-size: 12px; color: #666;">
                <p>Последнее обновление: {datetime.now().strftime('%H:%M:%S')}</p>
            </div>
        </body>
    </html>
    """

@app.route('/check')
def manual_check():
    """Ручная проверка"""
    discord_ok = check_discord()
    channels = check_channels()
    
    return {
        "discord": discord_status,
        "channels": channels,
        "time": datetime.now().isoformat()
    }

@app.route('/restart')
def soft_restart():
    """Мягкая перезагрузка"""
    global telegram_sent, discord_status
    telegram_sent = False
    discord_status = "🔄 Перезагрузка..."
    
    message = f"🔁 <b>Мягкая перезагрузка</b>\n\nВремя: {datetime.now().strftime('%H:%M:%S')}"
    send_telegram(message)
    
    return "✅ Перезагрузка запущена. <a href='/'>На главную</a>"

def self_pinger():
    """Самопинг"""
    time.sleep(30)
    while True:
        try:
            # Просто логируем раз в 10 пингов
            pass
        except:
            pass
        time.sleep(480)

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК ДИАГНОСТИЧЕСКОГО БОТА")
    logger.info(f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}")
    logger.info(f"🤖 Telegram Chat ID: {TELEGRAM_BOT_CHAT_ID}")
    logger.info(f"🔑 Discord Token: {'✅ Установлен' if DISCORD_TOKEN else '❌ Отсутствует'}")
    
    # Запускаем самопинг в фоне
    import threading
    ping_thread = threading.Thread(target=self_pinger, daemon=True)
    ping_thread.start()
    
    app.run(host='0.0.0.0', port=5000)
