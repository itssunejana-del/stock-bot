from flask import Flask, request, jsonify
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
import re
import json
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SEEDS_CHANNEL_ID = os.getenv('SEEDS_CHANNEL_ID')
RENDER_SERVICE_URL = os.getenv('RENDER_SERVICE_URL', 'https://stock-bot-cj4s.onrender.com')

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
# 🔴 СУПЕР-ЗАЩИТА ОТ DISCORD
discord_safety_mode = "ACTIVE"  # ACTIVE, COOLDOWN, EMERGENCY
discord_last_request_time = 0
discord_request_count = 0
discord_consecutive_errors = 0
discord_cooldown_until = 0
discord_emergency_until = 0

# MIN_REQUEST_INTERVAL в секундах по уровням безопасности
SAFETY_LEVELS = {
    "ACTIVE": 60,      # Раз в минуту (максимально безопасно)
    "COOLDOWN": 300,   # Раз в 5 минут (охлаждение)
    "EMERGENCY": 1800  # Раз в 30 минут (аварийный режим)
}

bot_start_time = datetime.now()
bot_status = "🟢 Инициализация"
channel_enabled = True
found_items_count = {}
telegram_offset = 0
last_error = None

check_lock = threading.Lock()

# ==================== СИСТЕМА БЕЗОПАСНОСТИ DISCORD ====================
def update_discord_safety(error_occurred=False, error_type=None):
    """Обновляет уровень безопасности Discord"""
    global discord_safety_mode, discord_consecutive_errors, discord_cooldown_until, discord_emergency_until
    
    current_time = time.time()
    
    if error_occurred:
        discord_consecutive_errors += 1
        logger.warning(f"⚠️ Ошибка Discord #{discord_consecutive_errors}")
        
        # 🔴 КРИТИЧЕСКАЯ ОШИБКА (пустой ответ/не-JSON)
        if error_type in ["empty_response", "json_error"]:
            logger.error("🚨 КРИТИЧЕСКАЯ ОШИБКА DISCORD - АВАРИЙНЫЙ РЕЖИМ")
            discord_safety_mode = "EMERGENCY"
            discord_emergency_until = current_time + 3600  # 1 час
            send_telegram_alert("🚨 КРИТИЧЕСКАЯ ОШИБКА DISCORD", "Аварийный режим на 1 час")
            return
        
        # 🔴 ОШИБКА ЛИМИТА (429)
        elif error_type == "rate_limit":
            if discord_consecutive_errors >= 2:
                discord_safety_mode = "EMERGENCY"
                discord_emergency_until = current_time + 1800  # 30 минут
                send_telegram_alert("🚨 ЛИМИТ DISCORD", "Аварийный режим на 30 минут")
            else:
                discord_safety_mode = "COOLDOWN"
                discord_cooldown_until = current_time + 900  # 15 минут
                send_telegram_alert("⚠️ ЛИМИТ DISCORD", "Охлаждение на 15 минут")
            return
        
        # 🔴 ДРУГАЯ ОШИБКА
        elif discord_consecutive_errors >= 3:
            discord_safety_mode = "COOLDOWN"
            discord_cooldown_until = current_time + 600  # 10 минут
            send_telegram_alert("⚠️ МНОГО ОШИБОК", "Охлаждение на 10 минут")
    
    # 🔵 ПРОВЕРКА ВРЕМЕНИ ВОССТАНОВЛЕНИЯ
    if discord_safety_mode == "EMERGENCY" and current_time >= discord_emergency_until:
        discord_safety_mode = "COOLDOWN"
        discord_cooldown_until = current_time + 600  # После аварии 10 минут охлаждения
        discord_consecutive_errors = 0
        logger.info("✅ Выход из аварийного режима")
        send_telegram_alert("✅ ВОССТАНОВЛЕНИЕ", "Выход из аварийного режима")
    
    if discord_safety_mode == "COOLDOWN" and current_time >= discord_cooldown_until:
        discord_safety_mode = "ACTIVE"
        discord_consecutive_errors = 0
        logger.info("✅ Возврат в активный режим")
        send_telegram_alert("✅ АКТИВНЫЙ РЕЖИМ", "Возобновление мониторинга")

def can_make_discord_request():
    """Можно ли делать запрос к Discord"""
    global discord_last_request_time, discord_safety_mode
    
    current_time = time.time()
    min_interval = SAFETY_LEVELS.get(discord_safety_mode, 60)
    
    # Проверяем интервал
    time_since_last = current_time - discord_last_request_time
    if time_since_last < min_interval:
        return False, f"Жду {min_interval - time_since_last:.0f} сек"
    
    # Проверяем ограничения режима
    if discord_safety_mode == "EMERGENCY":
        return False, "Аварийный режим"
    
    return True, "OK"

def safe_discord_request(url, headers, timeout=10):
    """Безопасный запрос к Discord API"""
    global discord_last_request_time, discord_request_count
    
    # 🔴 ПРОВЕРЯЕМ МОЖНО ЛИ ДЕЛАТЬ ЗАПРОС
    can_request, reason = can_make_discord_request()
    if not can_request:
        logger.debug(f"⏸️ Пропускаю запрос: {reason}")
        return None
    
    try:
        discord_request_count += 1
        discord_last_request_time = time.time()
        
        response = requests.get(url, headers=headers, timeout=timeout)
        
        # 🔴 ПУСТОЙ ОТВЕТ
        if not response.text or response.text.strip() == '':
            logger.error("❌ Discord вернул пустой ответ")
            update_discord_safety(error_occurred=True, error_type="empty_response")
            return None
        
        # 🔴 НЕ-JSON ОТВЕТ
        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.error("❌ Discord вернул не-JSON ответ")
            update_discord_safety(error_occurred=True, error_type="json_error")
            return None
        
        # 🔴 ОШИБКА ЛИМИТА (429)
        if response.status_code == 429:
            retry_after = data.get('retry_after', 5.0)
            logger.warning(f"⏳ Discord лимит. Жду {retry_after} сек.")
            update_discord_safety(error_occurred=True, error_type="rate_limit")
            time.sleep(retry_after)
            return None
        
        # 🔴 ДРУГИЕ ОШИБКИ
        if response.status_code != 200:
            logger.error(f"❌ Discord ошибка {response.status_code}")
            update_discord_safety(error_occurred=True, error_type="other")
            return None
        
        # ✅ УСПЕХ
        discord_consecutive_errors = 0  # Сбрасываем счётчик ошибок
        return data
        
    except requests.exceptions.Timeout:
        logger.warning("⏰ Таймаут Discord")
        update_discord_safety(error_occurred=True, error_type="other")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка Discord: {e}")
        update_discord_safety(error_occurred=True, error_type="other")
        return None

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML", disable_notification=False):
    """Отправляет сообщение в Telegram"""
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification
        }
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except:
        return False

def send_telegram_alert(title, message):
    """Отправляет уведомление о состоянии Discord"""
    if not TELEGRAM_BOT_CHAT_ID:
        return
    
    status_info = f"""
🔒 <b>СТАТУС БЕЗОПАСНОСТИ DISCORD</b>

<b>{title}</b>
{message}

📊 <b>Текущий режим:</b> {discord_safety_mode}
🔄 <b>Запросов сделано:</b> {discord_request_count}
⚠️ <b>Последних ошибок:</b> {discord_consecutive_errors}
🕐 <b>Следующий запрос через:</b> {SAFETY_LEVELS.get(discord_safety_mode, 60)} сек

📝 <b>Режимы безопасности:</b>
• 🟢 ACTIVE: запрос каждые 60 сек
• 🟡 COOLDOWN: запрос каждые 5 мин
• 🔴 EMERGENCY: запрос каждые 30 мин

✅ Бот продолжает работу, но мониторинг приостановлен.
"""
    
    send_telegram_message(TELEGRAM_BOT_CHAT_ID, status_info)

# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================
def fetch_kiro_messages():
    """Получает сообщения от Kiro с максимальной защитой"""
    if not DISCORD_TOKEN or not SEEDS_CHANNEL_ID:
        return None
    
    url = f"https://discord.com/api/v10/channels/{SEEDS_CHANNEL_ID}/messages?limit=2"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    
    data = safe_discord_request(url, headers, timeout=15)
    if not data:
        return None
    
    kiro_messages = []
    for msg in data:
        author = msg.get('author', {})
        username = author.get('username', '').lower()
        is_bot = author.get('bot', False)
        
        if ('kiro' in username) or (is_bot and 'kiro' in username):
            kiro_messages.append(msg)
    
    return kiro_messages if kiro_messages else None

def monitor_seeds_safe():
    """Мониторинг семян с максимальной безопасностью"""
    logger.info("🌱 Запуск безопасного мониторинга семян")
    
    while True:
        try:
            # 🔴 ПРОВЕРЯЕМ РЕЖИМ БЕЗОПАСНОСТИ
            current_time = time.time()
            
            if discord_safety_mode == "EMERGENCY":
                if current_time < discord_emergency_until:
                    remaining = discord_emergency_until - current_time
                    logger.warning(f"🚨 Аварийный режим: осталось {remaining/60:.1f} мин")
                    time.sleep(60)
                    continue
            
            elif discord_safety_mode == "COOLDOWN":
                if current_time < discord_cooldown_until:
                    remaining = discord_cooldown_until - current_time
                    logger.info(f"⏸️ Охлаждение: осталось {remaining/60:.1f} мин")
                    time.sleep(60)
                    continue
            
            # ✅ МОЖЕМ ПРОВЕРЯТЬ
            messages = fetch_kiro_messages()
            if messages:
                logger.info("📭 Kiro без семян (безопасный режим)")
            else:
                logger.debug("📭 Нет сообщений от Kiro")
            
            # 🔴 ЖДЁМ СОГЛАСНО РЕЖИМУ БЕЗОПАСНОСТИ
            sleep_time = SAFETY_LEVELS.get(discord_safety_mode, 60)
            logger.debug(f"💤 Безопасная пауза: {sleep_time} сек")
            time.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"💥 Ошибка мониторинга: {e}")
            time.sleep(60)

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    current_time = time.time()
    
    safety_info = ""
    if discord_safety_mode == "EMERGENCY":
        remaining = max(0, discord_emergency_until - current_time)
        safety_info = f"""
        <div class="card" style="background: #ffcccc;">
            <h2>🔴 АВАРИЙНЫЙ РЕЖИМ DISCORD</h2>
            <p><strong>Статус:</strong> 🔴 АКТИВЕН</p>
            <p><strong>Причина:</strong> Критическая ошибка Discord</p>
            <p><strong>Осталось:</strong> {remaining/60:.1f} минут</p>
            <p><strong>Запросы:</strong> Каждые 30 минут</p>
            <p><strong>Все запросы к Discord приостановлены</strong></p>
        </div>
        """
    elif discord_safety_mode == "COOLDOWN":
        remaining = max(0, discord_cooldown_until - current_time)
        safety_info = f"""
        <div class="card" style="background: #fff3cd;">
            <h2>🟡 РЕЖИМ ОХЛАЖДЕНИЯ DISCORD</h2>
            <p><strong>Статус:</strong> 🟡 АКТИВЕН</p>
            <p><strong>Причина:</strong> Много ошибок Discord</p>
            <p><strong>Осталось:</strong> {remaining/60:.1f} минут</p>
            <p><strong>Запросы:</strong> Каждые 5 минут</p>
            <p><strong>Ограниченный мониторинг</strong></p>
        </div>
        """
    else:
        safety_info = f"""
        <div class="card" style="background: #d4edda;">
            <h2>🟢 АКТИВНЫЙ РЕЖИМ</h2>
            <p><strong>Статус:</strong> 🟢 АКТИВЕН</p>
            <p><strong>Запросы:</strong> Каждые 60 секунд</p>
            <p><strong>Ошибок подряд:</strong> {discord_consecutive_errors}</p>
            <p><strong>Всего запросов:</strong> {discord_request_count}</p>
            <p><strong>Мониторинг работает нормально</strong></p>
        </div>
        """
    
    return f"""
    <html>
    <head>
        <title>🔒 Безопасный мониторинг Kiro</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .card {{ padding: 20px; border-radius: 10px; margin: 20px 0; }}
        </style>
    </head>
    <body>
        <h1>🔒 Безопасный мониторинг Kiro</h1>
        
        {safety_info}
        
        <div class="card" style="background: #f5f5f5;">
            <h2>📊 Статус системы</h2>
            <p><strong>Состояние:</strong> {bot_status}</p>
            <p><strong>Время работы:</strong> {str(datetime.now() - bot_start_time).split('.')[0]}</p>
            <p><strong>Режим Discord:</strong> {discord_safety_mode}</p>
            <p><strong>Запросов к Discord:</strong> {discord_request_count}</p>
            <p><strong>Последних ошибок:</strong> {discord_consecutive_errors}</p>
        </div>
        
        <div class="card" style="background: #f5f5f5;">
            <h2>🛡️ Система безопасности Discord</h2>
            <p><strong>Уровни безопасности:</strong></p>
            <ul>
                <li><strong>🟢 ACTIVE:</strong> Запрос каждые 60 секунд (нормальная работа)</li>
                <li><strong>🟡 COOLDOWN:</strong> Запрос каждые 5 минут (после ошибок)</li>
                <li><strong>🔴 EMERGENCY:</strong> Запрос каждые 30 минут (критическая ситуация)</li>
            </ul>
            <p><strong>Триггеры:</strong></p>
            <ul>
                <li>2 ошибки лимита подряд → 🔴 EMERGENCY (30 мин)</li>
                <li>Пустой ответ Discord → 🔴 EMERGENCY (60 мин)</li>
                <li>3 любые ошибки подряд → 🟡 COOLDOWN (10 мин)</li>
            </ul>
        </div>
        
        <div class="card" style="background: #f5f5f5;">
            <h2>🎯 Текущая стратегия</h2>
            <p><strong>Главный приоритет:</strong> Избежать бана Discord</p>
            <p><strong>Мониторинг:</strong> Безопасный, с большими интервалами</p>
            <p><strong>Скорость обнаружения:</strong> Второстепенная</p>
            <p><strong>Следующий шаг:</strong> Создать нового бота Discord</p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'discord_safety_mode': discord_safety_mode,
        'discord_request_count': discord_request_count,
        'discord_consecutive_errors': discord_consecutive_errors,
        'timestamp': datetime.now().isoformat()
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🔒 ЗАПУСК БЕЗОПАСНОГО МОНИТОРИНГА")
    logger.info("=" * 60)
    logger.info("🛡️ СИСТЕМА БЕЗОПАСНОСТИ DISCORD:")
    logger.info("   🟢 ACTIVE: запрос каждые 60 сек")
    logger.info("   🟡 COOLDOWN: запрос каждые 5 мин")
    logger.info("   🔴 EMERGENCY: запрос каждые 30 мин")
    logger.info("🎯 ПРИОРИТЕТ: Избежать бана Discord")
    logger.info("📅 СЛЕДУЮЩИЙ ШАГ: Создать нового бота Discord")
    logger.info("=" * 60)
    
    # Запускаем безопасный мониторинг
    monitor_thread = threading.Thread(target=monitor_seeds_safe, name='SafeMonitor', daemon=True)
    monitor_thread.start()
    
    # Отправляем уведомление о запуске
    startup_msg = """
🔒 <b>БЕЗОПАСНЫЙ МОНИТОРИНГ ЗАПУЩЕН</b>

🎯 <b>Главный приоритет:</b> Избежать бана Discord
⚠️ <b>Текущая ситуация:</b> Discord часто банил предыдущего бота

🛡️ <b>СИСТЕМА БЕЗОПАСНОСТИ:</b>
• 🟢 <b>ACTIVE:</b> Запрос каждые 60 секунд
• 🟡 <b>COOLDOWN:</b> Запрос каждые 5 минут (после ошибок)
• 🔴 <b>EMERGENCY:</b> Запрос каждые 30 минут (критично)

🔧 <b>Триггеры защиты:</b>
• 2 ошибки лимита подряд → Аварийный режим 30 мин
• Пустой ответ Discord → Аварийный режим 60 мин
• 3 любые ошибки подряд → Охлаждение 10 мин

📊 <b>Текущий режим:</b> ACTIVE
🔄 <b>Следующий запрос через:</b> 60 секунд

📅 <b>План действий:</b>
1. ✅ Запустить безопасный мониторинг
2. 🔜 Создать нового бота Discord
3. 🔜 Перейти на нового бота

✅ <b>Бот работает в безопасном режиме!</b>
Мониторинг продолжается с увеличенными интервалами.
"""
    send_telegram_message(TELEGRAM_BOT_CHAT_ID, startup_msg)
    
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
