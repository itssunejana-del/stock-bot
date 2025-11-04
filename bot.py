from flask import Flask, request
import requests
import os
import time
import logging
import threading
from datetime import datetime
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Токены и ID
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

# Глобальные переменные
last_processed_id = None
startup_time = datetime.now()
channel_enabled = True
bot_status = "🟢 Работает нормально"
last_error = None
processed_messages_cache = set()
telegram_offset = 0

def send_telegram_message(chat_id, text, parse_mode="HTML"):
    """Отправляет сообщение в указанный чат/канал"""
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены переменные Telegram")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id, 
            "text": text,
            "parse_mode": parse_mode
        }
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлено в Telegram ({chat_id}): {text[:100]}...")
            return True
        else:
            logger.error(f"❌ Ошибка Telegram {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def send_telegram_sticker(chat_id, sticker_id):
    """Отправляет стикер в Telegram"""
    if not TELEGRAM_TOKEN or not chat_id:
        logger.error("❌ Не настроены переменные Telegram")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {
            "chat_id": chat_id, 
            "sticker": sticker_id
        }
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"📱 Отправлен стикер в Telegram ({chat_id})")
            return True
        else:
            logger.error(f"❌ Ошибка отправки стикера {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Telegram: {e}")
        return False

def send_to_channel(text=None, sticker_id=None):
    """Отправляет сообщение или стикер в ТЕЛЕГРАМ КАНАЛ"""
    if not channel_enabled:
        logger.info("⏸️ Канал отключен, сообщение не отправлено")
        return False
        
    if sticker_id:
        return send_telegram_sticker(TELEGRAM_CHANNEL_ID, sticker_id)
    elif text:
        return send_telegram_message(TELEGRAM_CHANNEL_ID, text)
    else:
        return False

def send_to_bot(text):
    """Отправляет сообщение в ТЕЛЕГРАМ БОТА (личные сообщения)"""
    return send_telegram_message(TELEGRAM_BOT_CHAT_ID, text)

def send_help_message(chat_id):
    """Отправляет сообщение со списком команд"""
    help_text = (
        "🤖 <b>Бот мониторинга Grow a Garden</b>\n\n"
        "📋 <b>Доступные команды:</b>\n"
        "/start - Начать работу\n"
        "/status - Статус бота\n" 
        "/enable - Включить уведомления в канал\n"
        "/disable - Выключить уведомления в канал\n"
        "/help - Показать это сообщение\n\n"
        "🔄 Бот автоматически отслеживает стоки от Ember и присылает уведомления о томатах."
    )
    send_telegram_message(chat_id, help_text)

def send_bot_status(chat_id):
    """Отправляет статус бота"""
    global bot_status, last_error, channel_enabled
    
    uptime = datetime.now() - startup_time
    hours = uptime.total_seconds() / 3600
    
    status_text = (
        f"📊 <b>Статус бота</b>\n\n"
        f"{bot_status}\n"
        f"⏰ Время работы: {hours:.1f} часов\n"
        f"📅 Запущен: {startup_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"📢 Канал: {'✅ ВКЛЮЧЕН' if channel_enabled else '⏸️ ВЫКЛЮЧЕН'}\n"
        f"🔄 Отслеживаю: Ember bot\n"
        f"📝 Последнее сообщение: {last_processed_id or 'Еще не проверял'}\n"
    )
    
    if last_error:
        status_text += f"\n⚠️ <b>Последняя ошибка:</b>\n<code>{last_error}</code>"
    
    send_telegram_message(chat_id, status_text)

def handle_telegram_command(chat_id, command, message=None):
    """Обрабатывает команды Telegram"""
    global channel_enabled
    
    logger.info(f"🎯 Обрабатываю команду: {command} от {chat_id}")
    
    # 🔧 ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ID СТИКЕРА
    if message and 'sticker' in message:
        sticker = message['sticker']
        file_id = sticker['file_id']
        emoji = sticker.get('emoji', '')
        
        sticker_info = (
            f"🎯 <b>Информация о стикере:</b>\n"
            f"🆔 File ID: <code>{file_id}</code>\n"
            f"😊 Emoji: {emoji}\n\n"
            f"📋 <b>Для использования в коде:</b>\n"
            f"<code>tomato_sticker_id = \"{file_id}\"</code>"
        )
        send_telegram_message(chat_id, sticker_info)
        return
    
    if command == '/start':
        welcome_text = (
            "🎮 <b>Добро пожаловать!</b>\n\n"
            "Я бот для отслеживания стоков в игре <b>Grow a Garden</b>.\n"
            "Автоматически мониторю Discord канал с ботом Ember и присылаю уведомления о стоках.\n\n"
            "📱 <b>Вам в личные сообщения:</b> Все стоки от Ember\n"
            "📢 <b>В канал:</b> Только стикер при томате\n\n"
            "🎯 <b>Чтобы получить ID стикера:</b> Просто отправьте мне любой стикер!\n\n"
            "Используйте /help для списка команд."
        )
        send_telegram_message(chat_id, welcome_text)
        
    elif command == '/help':
        send_help_message(chat_id)
        
    elif command == '/status':
        send_bot_status(chat_id)
        
    elif command == '/enable':
        channel_enabled = True
        send_telegram_message(chat_id, "✅ <b>Уведомления в канал ВКЛЮЧЕНЫ</b>\nТеперь томаты будут приходить в канал.")
        
    elif command == '/disable':
        channel_enabled = False
        send_telegram_message(chat_id, "⏸️ <b>Уведомления в канал ВЫКЛЮЧЕНЫ</b>\nУведомления о томатах временно приостановлены.")
        
    else:
        send_telegram_message(chat_id, "❌ Неизвестная команда. Используйте /help для списка команд.")

def telegram_poller_safe():
    """Безопасный опросщик Telegram с защитой от конфликтов"""
    global telegram_offset
    
    logger.info("🔍 Запускаю безопасный Telegram поллер...")
    
    while True:
        try:
            # Сначала удаляем вебхук на всякий случай
            try:
                delete_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
                requests.get(delete_url, timeout=5)
            except:
                pass
            
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {
                'offset': telegram_offset + 1,
                'timeout': 30,
                'limit': 1
            }
            
            logger.info(f"🔄 Проверяю обновления (offset: {telegram_offset})")
            response = requests.get(url, params=params, timeout=35)
            
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
                            
                            # 🔧 Обрабатываем стикеры
                            if 'sticker' in message:
                                logger.info("📎 Получен стикер, обрабатываю...")
                                handle_telegram_command(chat_id, None, message)
                                continue
                                
                            if text.startswith('/'):
                                handle_telegram_command(chat_id, text)
                else:
                    time.sleep(2)
            else:
                if response.status_code == 409:
                    logger.warning("⚠️ Конфликт с другим экземпляром. Жду 30 секунд...")
                    time.sleep(30)
                else:
                    logger.error(f"❌ Ошибка Telegram API: {response.status_code}")
                    time.sleep(10)
            
        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            logger.error(f"💥 Ошибка в телеграм поллере: {e}")
            time.sleep(10)

def get_discord_messages():
    """Получает сообщения из Discord канала"""
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages?limit=10"
        headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            return response.json()
        else:
            error_msg = f"Ошибка Discord API: {response.status_code}"
            logger.error(f"❌ {error_msg}")
            return None
                
    except Exception as e:
        error_msg = f"Ошибка подключения к Discord: {e}"
        logger.error(f"💥 {error_msg}")
        return None

def clean_ember_text(text):
    """Очищает текст от эмодзи Discord и форматирует в красивый список"""
    # Удаляем эмодзи Discord формата <:name:123456>
    text = re.sub(r'<:[a-zA-Z0-9_]+:\d+>', '', text)
    
    # Удаляем лишние звездочки для жирного текста
    text = re.sub(r'\*\*', '', text)
    
    # Разделяем на строки и очищаем каждую
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if line and not line.startswith('Grow a Garden Stock') and not line.startswith('Seeds') and not line.startswith('Gear'):
            # Оставляем только название и количество
            if 'x' in line and any(char.isdigit() for char in line):
                cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def extract_all_text_from_message(message):
    """Извлекает ВЕСЬ текст из сообщения Ember включая fields"""
    content = message.get('content', '')
    embeds = message.get('embeds', [])
    
    all_text = content
    
    for embed in embeds:
        # Добавляем заголовок
        if embed.get('title'):
            all_text += f"\n{embed.get('title')}"
        
        # Добавляем описание
        if embed.get('description'):
            all_text += f"\n{embed.get('description')}"
        
        # 🔧 ВАЖНО: Добавляем поля (fields) - здесь томаты!
        for field in embed.get('fields', []):
            field_name = field.get('name', '')
            field_value = field.get('value', '')
            all_text += f"\n{field_name} {field_value}"
    
    return all_text

def format_ember_message(message):
    """Форматирует сообщение от Ember для Telegram"""
    content = message.get('content', '')
    embeds = message.get('embeds', [])
    
    full_text = content
    for embed in embeds:
        if embed.get('title'):
            full_text += f"\n\n{embed.get('title')}"
        if embed.get('description'):
            full_text += f"\n{embed.get('description')}"
        
        # 🔧 ВАЖНО: Добавляем поля (fields)
        for field in embed.get('fields', []):
            field_name = field.get('name', '')
            field_value = field.get('value', '')
            full_text += f"\n{field_name}: {field_value}"
    
    # Очищаем текст
    cleaned_text = clean_ember_text(full_text)
    
    return cleaned_text.strip()

def check_ember_messages(messages):
    """Проверяет сообщения от Ember бота"""
    global last_processed_id, bot_status, last_error, processed_messages_cache
    
    if not messages:
        return False
    
    try:
        messages.sort(key=lambda x: x['id'], reverse=True)
        
        found_tomato = False
        newest_id = messages[0]['id']
        
        if last_processed_id is None:
            last_processed_id = newest_id
            logger.info(f"🚀 Первый запуск. Запомнил сообщение: {last_processed_id}")
            send_to_bot("🚀 <b>Бот запущен и начал мониторинг!</b>")
            return False
        
        # Очищаем кэш если он слишком большой
        if len(processed_messages_cache) > 100:
            processed_messages_cache = set()
            logger.info("🧹 Очистил кэш обработанных сообщений")
        
        for message in messages:
            message_id = message['id']
            
            # Если дошли до уже обработанных - выходим
            if message_id <= last_processed_id:
                break
            
            # Защита от дублирования - проверяем в кэше
            if message_id in processed_messages_cache:
                logger.info(f"⏩ Пропускаем уже обработанное сообщение: {message_id}")
                continue
            
            author = message.get('author', {}).get('username', '')
            
            # Проверяем только сообщения от Ember бота
            if 'Ember' in author:
                logger.info(f"🔍 Новое сообщение от Ember: {message_id}")
                
                # 🔍 ДЕБАГ: Логируем ВСЮ структуру сообщения
                content = message.get('content', '')
                embeds = message.get('embeds', [])
                logger.info(f"📄 Основной текст: '{content}'")
                
                if embeds:
                    for i, embed in enumerate(embeds):
                        logger.info(f"📊 Embed {i}:")
                        logger.info(f"   Title: '{embed.get('title')}'")
                        logger.info(f"   Description: '{embed.get('description')}'")
                        
                        # 🔧 ВАЖНО: Логируем поля (fields)
                        fields = embed.get('fields', [])
                        logger.info(f"   Fields count: {len(fields)}")
                        for j, field in enumerate(fields):
                            logger.info(f"   Field {j}: name='{field.get('name')}', value='{field.get('value')}'")
                
                # Добавляем в кэш обработанных
                processed_messages_cache.add(message_id)
                
                # 🔧 Ищем томаты в ПОЛНОМ тексте (включая fields)
                full_search_text = extract_all_text_from_message(message)
                logger.info(f"🔎 Полный текст для поиска: {full_search_text[:500]}...")
                
                formatted_message = format_ember_message(message)
                
                if formatted_message:
                    # 📱 ВСЕГДА отправляем ВСЕ сообщения Ember в БОТА
                    bot_message = (
                        f"🛒 <b>Новый сток от Ember</b>\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
                        f"{formatted_message}"
                    )
                    send_to_bot(bot_message)
                    
                    # 🔍 Проверяем на наличие томата в ПОЛНОМ тексте
                    search_text_lower = full_search_text.lower()
                    logger.info(f"🔎 Ищу томат в тексте: {search_text_lower[:300]}...")
                    
                    tomato_keywords = ['tomato', 'томат', ':tomato']
                    found_keyword = None
                    
                    for keyword in tomato_keywords:
                        if keyword in search_text_lower:
                            found_keyword = keyword
                            break
                    
                    if found_keyword:
                        logger.info(f"🎯 ОБНАРУЖЕН ТОМАТ! Ключевое слово: '{found_keyword}'")
                        
                        # 📢 В КАНАЛ - СТИКЕР
                        tomato_sticker_id = "CAACAgIAAxkBAAEPszZpCfLc2HlDxyNpkHpQmxlBl94iwQACjYEAApqASUgobiA_uUJNkzYE"
                        
                        if send_to_channel(sticker_id=tomato_sticker_id):
                            logger.info("✅ Стикер о томате отправлен в канал!")
                        found_tomato = True
                    else:
                        logger.info("❌ Томат не найден в сообщении")
        
        last_processed_id = newest_id
        bot_status = "🟢 Работает нормально"
        last_error = None
        return found_tomato
        
    except Exception as e:
        error_msg = f"Ошибка обработки сообщений: {e}"
        logger.error(f"💥 {error_msg}")
        bot_status = "🔴 Ошибка обработки"
        last_error = error_msg
        send_to_bot(f"🚨 <b>Ошибка в мониторинге:</b>\n<code>{error_msg}</code>")
        return False

# ... остальные функции (monitor_discord, health_monitor, Flask routes) остаются без изменений ...

def start_background_threads():
    logger.info("🔄 Запускаю фоновые потоки...")
    
    threads = [
        threading.Thread(target=monitor_discord, daemon=True),
        threading.Thread(target=telegram_poller_safe, daemon=True),
        threading.Thread(target=health_monitor, daemon=True)
    ]
    
    for thread in threads:
        thread.start()
        logger.info(f"✅ Поток {thread.name} запущен")
    
    return threads

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК ИСПРАВЛЕННОГО БОТА!")
    logger.info("📱 Вам в бота: ВСЕ стоки от Ember")
    logger.info("📢 В канал: ТОЛЬКО стикер при томате")
    logger.info("🔧 ИСПРАВЛЕНИЕ: Теперь ищу томаты в fields embed'ов")
    
    # Запускаем фоновые потоки
    start_background_threads()
    
    # 📱 ТОЛЬКО В БОТА
    startup_msg_bot = (
        "🚀 <b>Бот запущен с исправлениями!</b>\n\n"
        "📱 <b>Вам в бота:</b> Все стоки от Ember\n"
        "📢 <b>В канал:</b> Только стикер при томате\n"
        "🔧 <b>Исправление:</b> Теперь ищу томаты в fields embed'ов\n\n"
        "🎛️ <b>Команды:</b>\n"
        "/start - Информация\n"
        "/status - Статус\n" 
        "/enable - Включить канал\n"
        "/disable - Выключить канал\n"
        "/help - Помощь\n\n"
        "🎯 <b>Чтобы получить ID стикера:</b> Просто отправьте мне стикер!"
    )
    
    send_to_bot(startup_msg_bot)
    
    app.run(host='0.0.0.0', port=5000)
