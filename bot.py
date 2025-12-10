from flask import Flask, request
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
import re
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Токены и ID
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# 🆕 МНОЖЕСТВЕННЫЕ КАНАЛЫ
DISCORD_CHANNEL_IDS = ['917417', '381036', '446956']
logger.info(f"📡 Настроено {len(DISCORD_CHANNEL_IDS)} каналов для мониторинга")

RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')

# 🆕 ОБНОВЛЕННЫЕ настройки отслеживаемых семян
TARGET_SEEDS = {
    'octobloom': {
        'keywords': ['octobloom', 'октоблум', ':octobloom'],
        'sticker_id': "CAACAgIAAxkBAAEP1btpIXhIEvgVEK4c6ugJv1EgP7UY-wAChokAAtZpCElVMcRUgb_jdDYE",
        'emoji': '🐙',
        'display_name': 'Octobloom'
    },
    'gem_egg': {
        'keywords': ['gem egg', 'gemegg', ':gemegg'],
        'sticker_id': "CAACAgIAAxkBAAEP1b9pIXhSl-ElpsKgOEEY-8oOmJ1qnAACI4MAAq6w2EinW-vu8EV_RzYE",
        'emoji': '💎',
        'display_name': 'Gem Egg'
    },
    'zebrazinkle': {
        'keywords': ['zebrazinkle', 'zebra zinkle', ':zebrazinkle'],
        'sticker_id': "CAACAgIAAxkBAAEPwjJpFDhW_6Vu29vF7DrTHFBcSf_WIAAC1XkAAkCXoUgr50G4SlzwrzYE",
        'emoji': '🦓',
        'display_name': 'Zebrazinkle'
    }
}

# 🆕 ИМЯ БОТА
BOT_NAME_TO_TRACK = "Kiro"

# Глобальные переменные
startup_time = datetime.now()
bot_status = "⚠️ АВАРИЙНЫЙ РЕЖИМ (Discord rate limit)"
last_error = "Discord API временно заблокирован (ошибка 429)"
channel_enabled = True
ping_count = 0
last_ping_time = None
found_seeds_count = {name: 0 for name in TARGET_SEEDS.keys()}

# 🆕 ВРЕМЯ БЛОКИРОВКИ
discord_blocked_until = startup_time + timedelta(hours=2)  # Блокировка на 2 часа
last_connection_test = None

def send_telegram_message(chat_id, text, parse_mode="HTML"):
    """Отправляет сообщение в Telegram"""
    if not TELEGRAM_TOKEN or not chat_id:
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, data=data, timeout=15)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено в Telegram: {text[:50]}...")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")
        return False

def send_to_bot(text):
    """Отправляет сообщение в бота"""
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

def self_pinger():
    """Самопинг чтобы Render не останавливал сервис"""
    global ping_count, last_ping_time
    
    time.sleep(30)
    
    while True:
        try:
            ping_count += 1
            last_ping_time = datetime.now()
            
            # Простой ping без ожидания ответа
            try:
                response = requests.get(f"{RENDER_SERVICE_URL}/", timeout=5)
                if response.status_code == 200:
                    logger.info(f"🏓 Самопинг #{ping_count} успешен")
                else:
                    logger.warning(f"⚠️ Самопинг: статус {response.status_code}")
            except:
                logger.info(f"🏓 Самопинг #{ping_count} (без проверки ответа)")
            
            time.sleep(480)  # 8 минут
            
        except Exception as e:
            logger.error(f"❌ Ошибка самопинга: {e}")
            time.sleep(60)

def test_discord_connection_safe():
    """Безопасная проверка подключения к Discord с защитой от rate limits"""
    global discord_blocked_until, last_connection_test, bot_status, last_error
    
    current_time = datetime.now()
    
    # Не проверяем слишком часто
    if last_connection_test and (current_time - last_connection_test).total_seconds() < 300:  # 5 минут
        return False
    
    # Проверяем, не истекла ли блокировка
    if current_time < discord_blocked_until:
        wait_seconds = (discord_blocked_until - current_time).total_seconds()
        logger.info(f"⏰ Discord все еще заблокирован. Жду еще {wait_seconds/60:.1f} минут")
        return False
    
    if not DISCORD_TOKEN:
        last_error = "Discord токен не установлен"
        return False
    
    try:
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        # ОЧЕНЬ медленный и осторожный запрос
        time.sleep(5)
        
        response = requests.get(
            "https://discord.com/api/v10/users/@me",
            headers=headers,
            timeout=30
        )
        
        last_connection_test = datetime.now()
        
        if response.status_code == 200:
            user_info = response.json()
            logger.info(f"✅ Discord доступен! Бот: {user_info.get('username')}")
            bot_status = "🟢 Discord восстановлен"
            last_error = None
            discord_blocked_until = current_time  # Снимаем блокировку
            return True
            
        elif response.status_code == 429:
            # Получаем время ожидания
            try:
                data = response.json()
                retry_after = data.get('retry_after', 3600)  # По умолчанию 1 час
            except:
                retry_after = 3600
            
            discord_blocked_until = current_time + timedelta(seconds=retry_after)
            last_error = f"Discord rate limit. Жду {retry_after/60:.1f} минут"
            logger.error(f"❌ Discord rate limit. Блокировка до: {discord_blocked_until}")
            bot_status = "⚠️ Discord rate limit"
            return False
            
        else:
            last_error = f"Discord ошибка: {response.status_code}"
            logger.error(f"❌ Discord ошибка: {response.status_code}")
            discord_blocked_until = current_time + timedelta(hours=1)
            return False
            
    except Exception as e:
        last_connection_test = datetime.now()
        last_error = f"Ошибка подключения: {e}"
        logger.error(f"❌ Ошибка проверки Discord: {e}")
        discord_blocked_until = current_time + timedelta(minutes=30)
        return False

def discord_connection_monitor():
    """Монитор восстановления соединения с Discord"""
    logger.info("🔍 Запускаю монитор восстановления Discord...")
    
    # Сразу отправляем уведомление о проблеме
    send_to_bot(
        "🚨 <b>АВАРИЙНЫЙ РЕЖИМ</b>\n\n"
        "Discord API временно заблокировал бота из-за слишком частых запросов.\n"
        "Это нормально при частых перезапусках на Render.\n\n"
        "🔄 <b>Бот перейдет в режим ожидания:</b>\n"
        "• Проверка Discord каждые 10 минут\n"
        "• Автоматическое восстановление при разблокировке\n"
        "• Уведомление при восстановлении\n\n"
        "⏱️ <b>Ожидаемое время восстановления:</b> 1-2 часа\n\n"
        "📊 <b>Текущий статус можно проверить командой:</b> /status"
    )
    
    while True:
        current_time = datetime.now()
        
        # Проверяем подключение
        if test_discord_connection_safe():
            # Восстановлено!
            send_to_bot(
                "✅ <b>DISCORD ВОССТАНОВЛЕН!</b>\n\n"
                "Соединение с Discord API восстановлено.\n"
                "Бот переходит в нормальный режим работы.\n\n"
                "🎯 <b>Начинаю мониторинг каналов...</b>"
            )
            break
        
        # Ждем перед следующей проверкой
        wait_time = 600  # 10 минут
        logger.info(f"💤 Ожидаю {wait_time/60} минут до следующей проверки Discord...")
        time.sleep(wait_time)

def telegram_poller_simple():
    """Простой обработчик Telegram команд"""
    global telegram_offset
    telegram_offset = 0
    
    time.sleep(10)
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {'offset': telegram_offset + 1, 'timeout': 10, 'limit': 1}
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok') and data.get('result'):
                    for update in data['result']:
                        telegram_offset = update['update_id']
                        
                        if 'message' in update:
                            msg = update['message']
                            chat_id = msg['chat']['id']
                            text = msg.get('text', '')
                            
                            if text == '/status':
                                send_bot_status(chat_id)
                            elif text == '/start':
                                send_welcome_message(chat_id)
                            elif text == '/help':
                                send_help_message(chat_id)
            
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"❌ Ошибка Telegram: {e}")
            time.sleep(10)

def send_bot_status(chat_id):
    """Отправляет статус бота"""
    global discord_blocked_until
    
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    current_time = datetime.now()
    
    # Рассчитываем оставшееся время блокировки
    if current_time < discord_blocked_until:
        wait_seconds = (discord_blocked_until - current_time).total_seconds()
        wait_time = f"{wait_seconds/60:.1f} минут"
        discord_status = f"🔴 ЗАБЛОКИРОВАН (ждем {wait_time})"
    else:
        discord_status = "🟢 ДОСТУПЕН"
        wait_time = "0 минут"
    
    seeds_stats = "\n".join([
        f"{config['emoji']} {config['display_name']}: {found_seeds_count.get(name, 0)}"
        for name, config in TARGET_SEEDS.items()
    ])
    
    last_ping_str = "Еще не было" if not last_ping_time else last_ping_time.strftime('%H:%M:%S')
    
    status_msg = (
        f"📊 <b>Статус бота (АВАРИЙНЫЙ РЕЖИМ)</b>\n\n"
        f"{bot_status}\n"
        f"📡 Discord: {discord_status}\n"
        f"⏱️ До разблокировки: ~{wait_time}\n"
        f"⏰ Время работы: {hours:.1f} часов\n"
        f"📅 Запущен: {startup_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"🤖 Отслеживаю: {BOT_NAME_TO_TRACK}\n"
        f"📡 Каналов: {len(DISCORD_CHANNEL_IDS)} шт\n"
        f"🏓 Самопинг: {ping_count} раз (последний: {last_ping_str})\n\n"
        f"🎯 <b>Найдено семян (до блокировки):</b>\n"
        f"{seeds_stats}\n\n"
    )
    
    if last_error:
        status_msg += f"⚠️ <b>Последняя ошибка:</b>\n<code>{last_error}</code>\n\n"
    
    status_msg += (
        f"🔄 <b>Что происходит:</b>\n"
        f"Discord временно заблокировал API из-за частых запросов.\n"
        f"Бот автоматически проверит восстановление через 10 минут.\n\n"
        f"⚙️ <b>Проверка Discord:</b> Каждые 10 минут\n"
        f"🔔 <b>Уведомление:</b> Придет автоматически при восстановлении"
    )
    
    send_telegram_message(chat_id, status_msg)

def send_welcome_message(chat_id):
    """Приветственное сообщение"""
    seeds_list = "\n".join([f"{config['emoji']} {config['display_name']}" 
                           for name, config in TARGET_SEEDS.items()])
    
    welcome_msg = (
        f"🎮 <b>Добро пожаловать!</b>\n\n"
        f"Я бот для отслеживания стоков в игре <b>Grow a Garden</b>.\n"
        f"📡 <b>В данный момент:</b> АВАРИЙНЫЙ РЕЖИМ\n"
        f"Discord API временно заблокирован из-за rate limits.\n\n"
        f"🔄 <b>Автоматическое восстановление:</b> Включено\n"
        f"⏱️ <b>Проверка:</b> Каждые 10 минут\n"
        f"🔔 <b>Уведомление:</b> Придет при восстановлении\n\n"
        f"🎯 <b>Отслеживаю семена:</b>\n"
        f"{seeds_list}\n\n"
        f"📡 <b>Мониторю каналы:</b> {len(DISCORD_CHANNEL_IDS)} шт\n\n"
        f"📋 <b>Команды:</b>\n"
        f"/start - Эта информация\n"
        f"/status - Текущий статус\n"
        f"/help - Помощь"
    )
    
    send_telegram_message(chat_id, welcome_msg)

def send_help_message(chat_id):
    """Сообщение помощи"""
    help_msg = (
        f"🤖 <b>Помощь по боту (АВАРИЙНЫЙ РЕЖИМ)</b>\n\n"
        f"📋 <b>Доступные команды:</b>\n"
        f"/start - Информация о боте\n"
        f"/status - Текущий статус и время до восстановления\n"
        f"/help - Это сообщение\n\n"
        f"🚨 <b>Текущая ситуация:</b>\n"
        f"Discord API временно заблокировал доступ из-за слишком частых запросов.\n"
        f"Это часто происходит при частых перезапусках на Render.\n\n"
        f"🔄 <b>Что делает бот:</b>\n"
        f"1. Ждет разблокировки Discord (1-2 часа)\n"
        f"2. Проверяет восстановление каждые 10 минут\n"
        f"3. Пришлет уведомление при восстановлении\n\n"
        f"⚙️ <b>Технические детали:</b>\n"
        f"• Ошибка: Discord API 429 (rate limit)\n"
        f"• Решение: Ожидание автоматического сброса лимитов\n"
        f"• Время: Обычно 1-2 часа\n\n"
        f"📞 <b>Если проблема сохраняется более 3 часов:</b>\n"
        f"1. Проверьте токен Discord в настройках Render\n"
        f"2. Убедитесь, что бот добавлен на сервер\n"
        f"3. Перезапустите сервис на Render"
    )
    
    send_telegram_message(chat_id, help_msg)

@app.route('/')
def home():
    """Главная страница"""
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    current_time = datetime.now()
    
    if current_time < discord_blocked_until:
        wait_seconds = (discord_blocked_until - current_time).total_seconds()
        discord_status = f"🔴 Заблокирован (ждем {wait_seconds/60:.1f} минут)"
    else:
        discord_status = "🟢 Доступен"
    
    return f"""
    <html>
        <head>
            <title>🌱 Seed Monitor - Аварийный режим</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                .status {{ background: #fff8e1; padding: 20px; border-radius: 10px; border-left: 5px solid #ff9800; }}
                .info {{ margin: 10px 0; }}
                .warning {{ background: #ffebee; padding: 15px; border-radius: 8px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <h1>🌱 Мониторинг семян - <span style="color: #ff9800;">АВАРИЙНЫЙ РЕЖИМ</span></h1>
            
            <div class="warning">
                <h3>⚠️ ВНИМАНИЕ: Discord API временно заблокирован</h3>
                <p>Из-за частых запросов Discord временно ограничил доступ.</p>
                <p>Бот автоматически проверит восстановление через 10 минут.</p>
            </div>
            
            <div class="status">
                <h3>📊 Статус системы</h3>
                <div class="info"><strong>Состояние:</strong> {bot_status}</div>
                <div class="info"><strong>Discord:</strong> {discord_status}</div>
                <div class="info"><strong>Время работы:</strong> {hours:.1f} часов</div>
                <div class="info"><strong>Запущен:</strong> {startup_time.strftime('%d.%m.%Y %H:%M')}</div>
                <div class="info"><strong>Самопинг:</strong> {ping_count} раз</div>
                <div class="info"><strong>Отслеживаемых каналов:</strong> {len(DISCORD_CHANNEL_IDS)}</div>
                <div class="info"><strong>Последняя ошибка:</strong> {last_error}</div>
            </div>
            
            <div style="margin-top: 30px;">
                <h3>🔄 Что происходит?</h3>
                <p>Discord имеет ограничения на количество запросов (rate limits).</p>
                <p>При частых перезапусках на Render эти лимиты быстро исчерпываются.</p>
                <p>Бот теперь:</p>
                <ul>
                    <li>Ждет автоматического сброса лимитов (1-2 часа)</li>
                    <li>Проверяет восстановление каждые 10 минут</li>
                    <li>Отправит уведомление в Telegram при восстановлении</li>
                </ul>
            </div>
        </body>
    </html>
    """

def start_background_threads():
    """Запускает фоновые потоки"""
    threads = [
        threading.Thread(target=discord_connection_monitor, daemon=True),
        threading.Thread(target=telegram_poller_simple, daemon=True),
        threading.Thread(target=self_pinger, daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Запущен поток: {thread.name}")
    
    return threads

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК БОТА В АВАРИЙНОМ РЕЖИМЕ")
    logger.info(f"📡 Каналы Discord: {len(DISCORD_CHANNEL_IDS)}")
    logger.info(f"🤖 Отслеживаю: {BOT_NAME_TO_TRACK}")
    logger.info("⚠️ Discord API временно заблокирован (ошибка 429)")
    logger.info("🔄 Будет проверять восстановление каждые 10 минут")
    logger.info("🔔 Уведомление придет в Telegram при восстановлении")
    
    start_background_threads()
    
    app.run(host='0.0.0.0', port=5000)
