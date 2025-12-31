from flask import Flask
import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
import re
import json
import random

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
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

# ==================== СЕМЕНА ====================
TARGET_ITEMS = {
    'octobloom': {
        'keywords': ['octobloom', 'октоблум', ':octobloom'],
        'sticker_id': "CAACAgIAAxkBAAEP1btpIXhIEvgVEK4c6ugJv1EgP7UY-wAChokAAtZpCElVMcRUgb_jdDYE",
        'emoji': '🐙',
        'display_name': 'Octobloom'
    },
    'zebrazinkle': {
        'keywords': ['zebrazinkle', 'zebra zinkle', ':zebrazinkle'],
        'sticker_id': "CAACAgIAAxkBAAEPwjJpFDhW_6Vu29vF7DrTHFBcSf_WIAAC1XkAAkCXoUgr50G4SlzwrzYE",
        'emoji': '🦓',
        'display_name': 'Zebrazinkle'
    },
    'firework_fern': {
        'keywords': ['firework fern', 'fireworkfern', ':fireworkfern', ':firework_fern:'],
        'sticker_id': "CAACAgIAAxkBAAEQHChpUBeOda8Uf0Uwig6BwvkW_z1ndAAC5Y0AAl8dgEoandjqAtpRWTYE",
        'emoji': '🎆',
        'display_name': 'Firework Fern'
    },
    'tomato_seeds': {
        'keywords': ['tomato seed', 'tomato seeds', 'томат', 'томаты', 'томатное семя'],
        'sticker_id': "CAACAgIAAxkBAAEPtFBpCrZ_mxXMfMmrjTZkBHN3Tpn9OAACf3sAAoEeWUgkKobs-st7ojYE",
        'emoji': '🍅',
        'display_name': 'Tomato Seeds (TEST)'
    }
}

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
bot_start_time = datetime.now()
bot_status = "🟢 Инициализация"
channel_enabled = True
found_items_count = {name: 0 for name in TARGET_ITEMS.keys()}
ping_count = 0
last_ping_time = None
telegram_offset = 0
last_error = None

current_cycle_start = None
cycle_found_stock = False
last_kiro_message_time = None
last_processed_message_id = None
SAFE_INTERVAL = 45  # Увеличил с 30 до 45 секунд

# АВАРИЙНЫЙ РЕЖИМ
discord_emergency_mode = False
discord_emergency_start = None
discord_error_count = 0
discord_last_error_time = None
EMERGENCY_COOLDOWN = 7200  # 2 часа вместо 1
MAX_ERRORS_BEFORE_EMERGENCY = 2
ERROR_WINDOW_SECONDS = 600  # 10 минут

sent_stickers_this_cycle = set()
STATE_FILE = 'bot_state.json'

# ==================== СОХРАНЕНИЕ СОСТОЯНИЯ ====================
def save_state():
    try:
        state = {
            'found_items_count': found_items_count,
            'last_kiro_message_time': last_kiro_message_time.isoformat() if last_kiro_message_time else None,
            'last_processed_message_id': last_processed_message_id,
            'ping_count': ping_count,
            'bot_status': bot_status,
            'discord_emergency_mode': discord_emergency_mode,
            'discord_emergency_start': discord_emergency_start.isoformat() if discord_emergency_start else None,
            'discord_error_count': discord_error_count,
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except:
        pass

def load_state():
    global found_items_count, last_kiro_message_time, last_processed_message_id
    global ping_count, bot_status, discord_emergency_mode, discord_emergency_start
    global discord_error_count
    
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
            
            found_items_count = state.get('found_items_count', found_items_count)
            ping_count = state.get('ping_count', ping_count)
            bot_status = state.get('bot_status', bot_status)
            last_processed_message_id = state.get('last_processed_message_id')
            
            time_str = state.get('last_kiro_message_time')
            if time_str:
                last_kiro_message_time = datetime.fromisoformat(time_str)
            
            discord_emergency_mode = state.get('discord_emergency_mode', False)
            emergency_start_str = state.get('discord_emergency_start')
            if emergency_start_str:
                discord_emergency_start = datetime.fromisoformat(emergency_start_str)
            discord_error_count = state.get('discord_error_count', 0)
    except:
        pass

# ==================== АВАРИЙНЫЙ РЕЖИМ ====================
def update_error_count():
    global discord_error_count, discord_last_error_time
    
    current_time = time.time()
    
    if discord_last_error_time and (current_time - discord_last_error_time > ERROR_WINDOW_SECONDS):
        discord_error_count = 0
    
    discord_error_count += 1
    discord_last_error_time = current_time
    
    if discord_error_count >= MAX_ERRORS_BEFORE_EMERGENCY:
        activate_emergency_mode()

def activate_emergency_mode():
    global discord_emergency_mode, discord_emergency_start, discord_error_count
    
    if not discord_emergency_mode:
        discord_emergency_mode = True
        discord_emergency_start = datetime.now()
        discord_error_count = 0
        
        emergency_msg = f"🚨 АВАРИЙНЫЙ РЕЖИМ на 2 часа. Ошибок: {MAX_ERRORS_BEFORE_EMERGENCY}"
        send_to_bot(emergency_msg)
        save_state()

def check_emergency_mode():
    global discord_emergency_mode, discord_emergency_start
    
    if not discord_emergency_mode:
        return True
    
    if discord_emergency_mode and discord_emergency_start:
        time_in_emergency = (datetime.now() - discord_emergency_start).total_seconds()
        
        if time_in_emergency >= EMERGENCY_COOLDOWN:
            discord_emergency_mode = False
            discord_emergency_start = None
            
            recovery_msg = "✅ Аварийный режим отключен"
            send_to_bot(recovery_msg)
            save_state()
            return True
    
    return False

# ==================== ЦИКЛЫ ====================
def get_current_cycle_start():
    now = datetime.now()
    cycle_minute = (now.minute // 5) * 5
    return now.replace(minute=cycle_minute, second=0, microsecond=0)

def parse_discord_timestamp(timestamp_str):
    try:
        if not timestamp_str:
            return None
        
        clean_str = timestamp_str
        if '.' in clean_str:
            clean_str = clean_str.split('.')[0]
        if clean_str.endswith('Z'):
            clean_str = clean_str[:-1] + '+00:00'
        return datetime.fromisoformat(clean_str)
    except:
        return None

def is_message_for_current_cycle(message, current_cycle_start_time):
    try:
        timestamp_str = message.get('timestamp')
        if not timestamp_str:
            return True
        
        message_time = parse_discord_timestamp(timestamp_str)
        if not message_time:
            return True
        
        previous_cycle_window_start = current_cycle_start_time - timedelta(seconds=30)
        return message_time >= previous_cycle_window_start
    except:
        return True

def should_check_now():
    global current_cycle_start, cycle_found_stock
    
    if not check_emergency_mode():
        return False, 300  # 5 минут если аварийный режим
    
    now = datetime.now()
    current_cycle = get_current_cycle_start()
    
    if current_cycle_start != current_cycle:
        current_cycle_start = current_cycle
        cycle_found_stock = False
        sent_stickers_this_cycle.clear()
    
    if cycle_found_stock:
        next_cycle = current_cycle + timedelta(minutes=5)
        seconds_left = (next_cycle - now).total_seconds()
        return False, min(seconds_left, 300)
    
    seconds_in_cycle = (now - current_cycle_start).total_seconds()
    check_window = 3
    seconds_mod = seconds_in_cycle % SAFE_INTERVAL
    
    if seconds_mod < check_window:
        seconds_until_next_check = SAFE_INTERVAL - seconds_mod
        return True, seconds_until_next_check
    
    seconds_to_next_check = SAFE_INTERVAL - (seconds_in_cycle % SAFE_INTERVAL)
    return False, min(seconds_to_next_check, 300)

# ==================== TELEGRAM ====================
def send_telegram_message(chat_id, text, parse_mode="HTML", disable_notification=False):
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
        
        if response.status_code == 200:
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            time.sleep(retry_after)
            return False
        else:
            return False
    except:
        return False

def send_telegram_sticker(chat_id, sticker_id, disable_notification=True):
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {
            "chat_id": chat_id,
            "sticker": sticker_id,
            "disable_notification": disable_notification
        }
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            time.sleep(retry_after)
            return False
        else:
            return False
    except:
        return False

def send_to_channel(sticker_id=None, text=None):
    if not channel_enabled or not TELEGRAM_CHANNEL_ID:
        return False
    
    if not hasattr(send_to_channel, 'last_send_time'):
        send_to_channel.last_send_time = 0
    
    current_time = time.time()
    if current_time - send_to_channel.last_send_time < 3:
        time.sleep(3)
    
    send_to_channel.last_send_time = time.time()
    
    if sticker_id:
        return send_telegram_sticker(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    
    return False

def send_to_bot(text, disable_notification=False):
    if not TELEGRAM_BOT_CHAT_ID:
        return False
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text, disable_notification=disable_notification)

# ==================== DISCORD ====================
def safe_discord_request(limit=5):  # Уменьшил с 10 до 5
    global last_error
    
    if not DISCORD_TOKEN or not SEEDS_CHANNEL_ID:
        return None
    
    if not check_emergency_mode():
        return None
    
    try:
        time.sleep(3 + random.random() * 3)  # Увеличил задержку
        
        url = f"https://discord.com/api/v10/channels/{SEEDS_CHANNEL_ID}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            if not response.text or response.text.strip() == '':
                return None
            
            try:
                data = response.json()
                last_error = None
                return data
            except:
                return None
                
        elif response.status_code == 429:
            retry_after = 10.0  # Минимум 10 секунд
            try:
                retry_data = response.json()
                retry_after = max(10.0, retry_data.get('retry_after', 10.0))
            except:
                pass
            
            last_error = f"Discord 429: жду {retry_after} сек"
            update_error_count()
            time.sleep(retry_after + 5)  # +5 секунд для безопасности
            return None
            
        else:
            last_error = f"Discord ошибка {response.status_code}"
            update_error_count()
            return None
            
    except requests.exceptions.Timeout:
        last_error = "Discord таймаут"
        update_error_count()
        return None
    except:
        last_error = "Ошибка Discord"
        update_error_count()
        return None

def extract_text_from_message(message):
    full_text = message.get('content', '').lower()
    
    for embed in message.get('embeds', []):
        if embed.get('title'):
            full_text += ' ' + embed.get('title', '').lower()
        if embed.get('description'):
            full_text += ' ' + embed.get('description', '').lower()
        for field in embed.get('fields', []):
            full_text += ' ' + field.get('name', '').lower()
            full_text += ' ' + field.get('value', '').lower()
    
    return full_text

def process_discord_messages():
    global cycle_found_stock, last_kiro_message_time, last_processed_message_id
    global found_items_count, bot_status, last_error
    
    if not check_emergency_mode():
        return False
    
    messages = safe_discord_request(limit=5)
    if not messages:
        return False
    
    found_any_item = False
    current_time = datetime.now()
    current_cycle_start_time = get_current_cycle_start()
    
    messages.sort(key=lambda x: x['id'], reverse=False)
    
    for message in messages:
        message_id = message['id']
        
        if last_processed_message_id and int(message_id) <= int(last_processed_message_id):
            continue
        
        author_name = message.get('author', {}).get('username', '').lower()
        if 'kiro' not in author_name:
            continue
        
        if not is_message_for_current_cycle(message, current_cycle_start_time):
            last_processed_message_id = message_id
            continue
        
        last_kiro_message_time = current_time
        last_processed_message_id = message_id
        text = extract_text_from_message(message)
        
        found_items_this_message = []
        
        for item_name, item_config in TARGET_ITEMS.items():
            for keyword in item_config['keywords']:
                if keyword in text:
                    found_items_count[item_name] += 1
                    found_items_this_message.append(item_config)
                    break
        
        if found_items_this_message:
            for item_config in found_items_this_message:
                if item_config['sticker_id'] in sent_stickers_this_cycle:
                    continue
                
                time_str = current_time.strftime('%H:%M:%S')
                cycle_str = current_cycle_start_time.strftime('%H:%M')
                
                notification = (
                    f"🎯 НАЙДЕН {item_config['emoji']} {item_config['display_name']}\n"
                    f"Время: {time_str}\nЦикл: {cycle_str}"
                )
                
                send_to_bot(notification, disable_notification=False)
                
                if send_to_channel(sticker_id=item_config['sticker_id']):
                    sent_stickers_this_cycle.add(item_config['sticker_id'])
                
                found_any_item = True
            
            cycle_found_stock = True
            bot_status = f"🟢 Найден сток в цикле {current_cycle_start_time.strftime('%H:%M')}"
            save_state()
            return True
        
        cycle_found_stock = True
        bot_status = f"🟡 Kiro без семян"
        
        time_str = current_time.strftime('%H:%M:%S')
        empty_notification = f"📭 Kiro без семян в {time_str}"
        send_to_bot(empty_notification, disable_notification=True)
        
        save_state()
        return True
    
    return False

# ==================== МОНИТОРИНГ ====================
def smart_monitor():
    time.sleep(30)
    
    while True:
        try:
            should_check, wait_seconds = should_check_now()
            
            if should_check:
                found = process_discord_messages()
            
            if wait_seconds > 0:
                time.sleep(min(wait_seconds, 10))
            else:
                time.sleep(5)
            
        except:
            time.sleep(30)

def self_pinger():
    time.sleep(60)
    
    while True:
        try:
            ping_count = 0
            if RENDER_SERVICE_URL:
                try:
                    requests.get(f"{RENDER_SERVICE_URL}/health", timeout=5)
                except:
                    pass
        except:
            pass
        
        time.sleep(300)  # 5 минут

def telegram_poller():
    global telegram_offset
    
    time.sleep(10)
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {'offset': telegram_offset + 1, 'timeout': 10, 'limit': 1}
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok') and data.get('result'):
                    updates = data['result']
                    for update in updates:
                        telegram_offset = update['update_id']
                        if 'message' in update:
                            message = update['message']
                            chat_id = message['chat']['id']
                            text = message.get('text', '')
                            if text == '/status':
                                send_to_bot("Бот работает", disable_notification=True)
            
            time.sleep(10)
        except:
            time.sleep(10)

# ==================== ВЕБ ====================
@app.route('/')
def home():
    return "🌱 Бот работает"

@app.route('/health')
def health_check():
    return "OK"

@app.route('/status')
def status_page():
    return "Статус: OK"

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    load_state()
    
    logger.info("Запуск бота")
    
    threads = [
        threading.Thread(target=smart_monitor, daemon=True),
        threading.Thread(target=self_pinger, daemon=True),
        threading.Thread(target=telegram_poller, daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        time.sleep(1)
    
    send_to_bot("🤖 Бот запущен")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
