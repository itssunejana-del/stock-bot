from flask import Flask, request, jsonify
import requests
import os
import time
import json
from datetime import datetime

app = Flask(__name__)

# Telegram настройки
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Отслеживаемые предметы
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
    }
}

# Глобальные переменные
startup_time = datetime.now()
found_items_count = {name: 0 for name in TARGET_ITEMS.keys()}
channel_enabled = True

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram_message(chat_id, text, parse_mode="HTML"):
    """Отправляет сообщение в Telegram"""
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": False
        }
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except:
        return False

def send_telegram_sticker(chat_id, sticker_id):
    """Отправляет стикер в Telegram"""
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {
            "chat_id": chat_id,
            "sticker": sticker_id,
            "disable_notification": True
        }
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except:
        return False

def send_to_bot(text):
    """Отправляет сообщение в ТЕЛЕГРАМ БОТА"""
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

def send_to_channel(sticker_id=None, text=None):
    """Отправляет в ТЕЛЕГРАМ КАНАЛ"""
    if not channel_enabled or not TELEGRAM_CHANNEL_ID:
        return False
    
    if sticker_id:
        return send_telegram_sticker(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    return False

# ==================== ОБРАБОТКА WEBHOOK ====================
def check_for_items(content):
    """Проверяет есть ли в сообщении отслеживаемые предметы"""
    content_lower = content.lower()
    found_items = []
    
    for item_name, item_config in TARGET_ITEMS.items():
        for keyword in item_config['keywords']:
            if keyword in content_lower:
                found_items.append(item_name)
                break
    
    return found_items

@app.route('/webhook/discord', methods=['POST'])
def discord_webhook():
    """Обрабатывает вебхук от Discord"""
    try:
        data = request.json
        print(f"[WEBHOOK] Получен запрос")
        
        # Проверяем что это сообщение
        if 'content' not in data or 'author' not in data:
            print(f"[WEBHOOK] Игнорируем: нет content/author")
            return jsonify({'status': 'ignored'}), 200
        
        # Получаем данные
        author = data.get('author', {})
        author_name = author.get('username', '').lower()
        author_bot = author.get('bot', False)
        content = data.get('content', '')
        
        # Проверяем что сообщение от Kiro
        is_kiro = ('kiro' in author_name) or (author_bot and 'kiro' in str(author))
        
        if not is_kiro:
            print(f"[WEBHOOK] Игнорируем: не Kiro ({author_name})")
            return jsonify({'status': 'ignored', 'reason': 'not kiro'}), 200
        
        print(f"[WEBHOOK] Сообщение от Kiro: {content[:100]}...")
        
        # Проверяем на предметы
        found_items = check_for_items(content)
        
        if found_items:
            current_time = datetime.now().strftime('%H:%M:%S')
            
            # Обновляем счётчики
            for item_name in found_items:
                found_items_count[item_name] += 1
            
            # Формируем сообщение для бота
            items_list = []
            for item_name in found_items:
                item = TARGET_ITEMS[item_name]
                items_list.append(f"{item['emoji']} {item['display_name']}")
            
            bot_message = f"🎯 <b>Найдены предметы в {current_time}</b>\n"
            bot_message += f"📝 {', '.join(items_list)}\n\n"
            bot_message += f"<code>{content[:500]}</code>"
            
            # Отправляем в бота
            send_to_bot(bot_message)
            
            # Отправляем стикеры в канал
            for item_name in found_items:
                item = TARGET_ITEMS[item_name]
                send_to_channel(sticker_id=item['sticker_id'])
                time.sleep(1)  # Пауза между стикерами
            
            print(f"[WEBHOOK] Отправлены уведомления: {found_items}")
        
        return jsonify({'status': 'processed', 'found_items': found_items}), 200
        
    except Exception as e:
        print(f"[WEBHOOK] Ошибка: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    uptime = datetime.now() - startup_time
    
    items_stats = "\n".join([
        f"{TARGET_ITEMS[name]['emoji']} {TARGET_ITEMS[name]['display_name']}: {count}"
        for name, count in found_items_count.items() if count > 0
    ])
    
    return f"""
    <html>
        <head>
            <title>🌱 Webhook мониторинг Kiro</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .card {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <h1>🌱 Discord Webhook мониторинг Kiro</h1>
            
            <div class="card">
                <h3>📊 Статус системы</h3>
                <p><strong>Время работы:</strong> {str(uptime).split('.')[0]}</p>
                <p><strong>Канал Telegram:</strong> {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}</p>
                <p><strong>Webhook URL:</strong> <code>/webhook/discord</code></p>
            </div>
            
            <div class="card">
                <h3>🎯 Отслеживаемые предметы (3 семена)</h3>
                <ul>
                    <li>🐙 Octobloom (octobloom, октоблум)</li>
                    <li>🦓 Zebrazinkle (zebrazinkle, zebra zinkle)</li>
                    <li>🎆 Firework Fern (firework fern, fireworkfern)</li>
                </ul>
            </div>
            
            <div class="card">
                <h3>🏆 Найдено предметов</h3>
                <pre>{items_stats if items_stats else "Еще не найдено"}</pre>
            </div>
            
            <div class="card">
                <h3>🔧 Как работает</h3>
                <p>1. Discord отправляет ВСЕ сообщения на наш вебхук</p>
                <p>2. Мы фильтруем только сообщения от Kiro</p>
                <p>3. Если находим семена - отправляем в Telegram</p>
                <p>4. <b>Нет лимитов Discord API!</b> 🎉</p>
            </div>
        </body>
    </html>
    """

@app.route('/enable')
def enable_channel():
    global channel_enabled
    channel_enabled = True
    return "✅ Канал Telegram включен"

@app.route('/disable')
def disable_channel():
    global channel_enabled
    channel_enabled = False
    return "⏸️ Канал Telegram выключен"

@app.route('/health')
def health():
    return jsonify({
        'status': 'running',
        'startup_time': startup_time.isoformat(),
        'found_items': found_items_count,
        'channel_enabled': channel_enabled
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    
    print("=" * 60)
    print("🚀 Discord Webhook мониторинг Kiro запущен!")
    print("=" * 60)
    print("🎯 Отслеживаю 3 семена:")
    print("   🐙 Octobloom, 🦓 Zebrazinkle, 🎆 Firework Fern")
    print("🌐 Webhook URL: http://ваш-сервер:{port}/webhook/discord")
    print("📱 Telegram уведомления: ВКЛЮЧЕНЫ")
    print("✅ Без лимитов Discord API!")
    print("=" * 60)
    
    # Отправляем уведомление о запуске
    startup_msg = """
🚀 <b>Discord Webhook мониторинг запущен!</b>

🎯 <b>Без лимитов Discord API!</b>
• Discord сам отправляет сообщения
• Нет токена бота = нет банов
• Вебхуки на все 3 канала

📊 <b>Отслеживаю 3 семена:</b>
• 🐙 Octobloom
• 🦓 Zebrazinkle  
• 🎆 Firework Fern

🌐 <b>Webhook URL:</b> /webhook/discord
📱 <b>Telegram:</b> ВКЛЮЧЕН

✅ <b>Готов к работе!</b>
Discord будет присылать все сообщения, мы отфильтруем только Kiro.
"""
    send_to_bot(startup_msg)
    
    app.run(host='0.0.0.0', port=port, debug=False)
