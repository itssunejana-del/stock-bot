#!/usr/bin/env python3
"""
Резервный селф-бот для мониторинга стока
С приоритетом на эмбеды и поддержкой всех ролей
"""

import discord
import os
import asyncio
import requests
import random
import time
from datetime import datetime
import logging
import html
import re
import json

from flask import Flask
import threading

# ==================== ВЕБ-СЕРВЕР ДЛЯ RENDER ====================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=10000)

# Запускаем Flask в отдельном потоке
threading.Thread(target=run_web, daemon=True).start()

# ==================== НАСТРОЙКА ЛОГГИРОВАНИЯ ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
STOCKS_TELEGRAM_CHANNEL = os.getenv('STOCKS_TELEGRAM_CHANNEL')

# ==================== СЛОВАРЬ РОЛЕЙ ====================
# Только те, что нужны для поиска и проверки
ROLE_NAMES = {
    '1426610862591840266': 'Cherry',   # 🍒
    '1442312884859179049': 'Cabbage',  # 🥬
    '1477643000073949214': 'Bamboo',   # 🎋
    '1477643077882609755': 'Mango',    # 🥭
    '1439345675690049666': 'Carrot',   # 🥕 для проверки
    '1392620784870101002': 'Mushroom', # 🍄 для контекста
    '1392622053278093473': 'Onion',    # 🧅 для контекста
    '1392622157460144198': 'Corn',     # 🌽 для контекста
}

# ==================== ЦЕЛЕВЫЕ ПРЕДМЕТЫ ====================
# Только для этих будут стикеры
TARGET_ITEMS = {
    'cherry': {
        'keywords': ['cherry', '🍒'],
        'sticker_id': "CAACAgIAAxkBAAEQnoFpnyHlfKoDssWIpZHbKrjgBUkgAQACy5AAAv894EjYncv41k4_XzoE",
        'emoji': '🍒',
        'display_name': 'Cherry'
    },
    'cabbage': {
        'keywords': ['cabbage', '🥬'],
        'sticker_id': "CAACAgIAAxkBAAEQnoNpnyHvhLutfLJmqqqqk8_TWy-8wAACZ5YAAho06UipuXAdrrQYXToE",
        'emoji': '🥬',
        'display_name': 'Cabbage'
    },
    'bamboo': {
        'keywords': ['bamboo', '🎋'],
        'sticker_id': "CAACAgIAAxkBAAEQpw1ppGFmoB8w-C71IZOkeBOG029w5QAC4psAAsOUIEnsw-M936B9BjoE",
        'emoji': '🎋',
        'display_name': 'Bamboo'
    },
    'mango': {
        'keywords': ['mango', '🥭'],
        'sticker_id': "CAACAgIAAxkBAAEQpw9ppGFstEgOkpR-HLILv_ugOZVViQACkZYAAu_cIUnaEdl_e13gzDoE",
        'emoji': '🥭',
        'display_name': 'Mango'
    }
}

# ==================== ФАЙЛ СОСТОЯНИЯ ====================
STATE_FILE = 'bot_state.json'

def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {'processed_messages': []}

def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except:
        pass

# ==================== TELEGRAM ФУНКЦИИ ====================
def send_telegram(chat_id, text, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Telegram отправлено")
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram, жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Telegram ошибка {response.status_code}")
            return False
    except Exception as e:
        logger.error(f'❌ Telegram error: {e}')
        return False

def send_telegram_sticker(chat_id, sticker_id):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {"chat_id": chat_id, "sticker": sticker_id}
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f'❌ Sticker error: {e}')
        return False

# ==================== УНИВЕРСАЛЬНЫЙ ПАРСЕР ====================
def extract_full_content(message):
    """Парсер с приоритетом на эмбеды - сначала самое важное!"""
    full_content = ""
    
    # 1. СНАЧАЛА эмбеды - это самое важное (сток)!
    if message.embeds:
        for embed in message.embeds:
            if embed.title:
                full_content += f"{embed.title}\n"
            if embed.description:
                desc = embed.description
                for role_id, role_name in ROLE_NAMES.items():
                    desc = desc.replace(f'<@&{role_id}>', role_name)
                full_content += f"{desc}\n"
            if embed.fields:
                for field in embed.fields:
                    field_name = field.name
                    field_value = field.value
                    for role_id, role_name in ROLE_NAMES.items():
                        field_name = field_name.replace(f'<@&{role_id}>', role_name)
                        field_value = field_value.replace(f'<@&{role_id}>', role_name)
                    full_content += f"{field_name}: {field_value}\n"
    
    # 2. ПОТОМ обычный текст сообщения
    if message.content:
        content = message.content
        for role_id, role_name in ROLE_NAMES.items():
            content = content.replace(f'<@&{role_id}>', role_name)
        full_content += f"{content}\n"
    
    # 3. system_content (если есть)
    if hasattr(message, 'system_content') and message.system_content:
        full_content += f"{message.system_content}\n"
    
    # 4. clean_content (если есть)
    if hasattr(message, 'clean_content') and message.clean_content:
        clean = message.clean_content
        for role_id, role_name in ROLE_NAMES.items():
            clean = clean.replace(f'<@&{role_id}>', role_name)
        full_content += f"{clean}\n"
    
    # 5. Компоненты (кнопки) - добавляем, но помечаем, что это кнопки
    if hasattr(message, 'components') and message.components:
        for component in message.components:
            if hasattr(component, 'children'):
                for child in component.children:
                    if hasattr(child, 'label') and child.label:
                        # Добавляем, но с пометкой, чтобы не путать со стоком
                        full_content += f"[Кнопка: {child.label}]\n"
    
    # Очистка от лишнего
    full_content = re.sub(r'<:[^:]+:\d+>', '', full_content)
    full_content = re.sub(r'\*\*', '', full_content)
    full_content = re.sub(r'<t:\d+:[A-Za-z]+>', '', full_content)
    full_content = html.escape(full_content)
    full_content = '\n'.join([line.strip() for line in full_content.split('\n') if line.strip()])
    
    return full_content.strip()

# ==================== ОСНОВНОЙ КЛАСС БОТА ====================
class SelfBot(discord.Client):
    def __init__(self):
        super().__init__()
        
        # Загружаем состояние
        state = load_state()
        self.processed_messages = set(state.get('processed_messages', []))
        self.found_items_count = {name: 0 for name in TARGET_ITEMS.keys()}
        self.channel_id = int(os.getenv('STOCKS_CHANNEL_ID'))
        self.max_cache_size = 100
        self.started = False
        self.last_error_time = None
        self.polling_task = None
        
    async def on_ready(self):
        logger.info(f'✅ Резервный селф-бот {self.user} запущен!')
        
        # Тестовое сообщение при запуске
        current_time = datetime.now().strftime('%H:%M:%S')
        test_message = (
            f"🤖 <b>Бот запущен!</b>\n"
            f"⏰ Время: {current_time}\n"
            f"📊 Статус: ✅ Подключен к Discord\n"
            f"📡 Канал: {self.channel_id}\n"
            f"💾 В памяти: {len(self.processed_messages)} сообщений\n\n"
            f"🔍 Отслеживаю: 🍒 🥬 🎋 🥭\n"
            f"📋 Для проверки: 🥕 Carrot"
        )
        send_telegram(TELEGRAM_BOT_CHAT_ID, test_message)
        
        # Сохраняем состояние каждые 5 минут
        self.loop.create_task(self.auto_save())
        
        # Запускаем polling (как запасной вариант)
        self.polling_task = self.loop.create_task(self.poll_channel())
    
    async def auto_save(self):
        """Автоматическое сохранение состояния"""
        while not self.is_closed():
            await asyncio.sleep(300)  # 5 минут
            state = {'processed_messages': list(self.processed_messages)[-self.max_cache_size:]}
            save_state(state)
            logger.info("💾 Состояние сохранено")
    
    async def poll_channel(self):
        """Запасной polling на случай пропущенных сообщений"""
        await self.wait_until_ready()
        
        while not self.is_closed():
            try:
                channel = self.get_channel(self.channel_id)
                if not channel:
                    logger.error(f"❌ Канал {self.channel_id} не найден")
                    await asyncio.sleep(60)
                    continue
                
                # Получаем последние 3 сообщения
                messages = []
                async for msg in channel.history(limit=3):
                    messages.append(msg)
                
                for message in messages:
                    if message.id in self.processed_messages:
                        continue
                    
                    if 'dawn' not in message.author.name.lower():
                        continue
                    
                    logger.info(f"📨 Polling нашел сообщение {message.id}")
                    await self.process_stock_message(message)
                    
                    self.processed_messages.add(message.id)
                    if len(self.processed_messages) > self.max_cache_size:
                        self.processed_messages.pop()
                
                # Случайная задержка 25-35 секунд
                delay = random.uniform(25, 35)
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в poll_channel: {e}")
                await asyncio.sleep(60)
    
    async def on_message(self, message):
        """Обработка новых сообщений (WebSocket)"""
        try:
            # Проверяем канал
            if message.channel.id != self.channel_id:
                return
            
            # Проверяем автора
            if 'dawn' not in message.author.name.lower():
                return
            
            # Защита от дублей
            if message.id in self.processed_messages:
                logger.info(f"⏭️ Дубль сообщения {message.id}")
                return
            
            logger.info(f"📨 НОВОЕ сообщение от Dawn (ID: {message.id})")
            
            # Обрабатываем сообщение
            await self.process_stock_message(message)
            
            # Добавляем в обработанные
            self.processed_messages.add(message.id)
            if len(self.processed_messages) > self.max_cache_size:
                self.processed_messages.pop()
            
            # Сохраняем состояние
            state = {'processed_messages': list(self.processed_messages)[-self.max_cache_size:]}
            save_state(state)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в on_message: {e}")
            await self.handle_error(f"Ошибка обработки сообщения: {e}")
    
    async def on_disconnect(self):
        """При отключении от Discord"""
        logger.warning("⚠️ Отключение от Discord")
        await self.handle_error("⚠️ Потеря соединения с Discord. Переподключаюсь...")
    
    async def on_error(self, event, *args, **kwargs):
        """Обработка ошибок Discord"""
        logger.error(f"❌ Ошибка Discord: {event}")
        await self.handle_error(f"Ошибка Discord: {event}")
    
    async def handle_error(self, error_text):
        """Отправка уведомления об ошибке (не чаще раза в минуту)"""
        now = datetime.now()
        if self.last_error_time and (now - self.last_error_time).seconds < 60:
            return
        
        self.last_error_time = now
        send_telegram(TELEGRAM_BOT_CHAT_ID, f"🚨 <b>ВНИМАНИЕ!</b>\n{error_text}")
    
    async def process_stock_message(self, message):
        """Обработка сообщения со стоком"""
        try:
            logger.info(f"🔍 Обработка сообщения {message.id}")
            
            full_content = extract_full_content(message)
            
            # Логируем результат парсинга
            if full_content:
                logger.info(f"✅ Текст извлечен: {full_content[:100]}...")
            else:
                logger.warning("❌ НЕ УДАЛОСЬ извлечь текст")
                send_telegram(TELEGRAM_BOT_CHAT_ID, f"⚠️ Не удалось извлечь текст из сообщения {message.id}")
                return
            
            # Поиск целевых предметов
            found_items = []
            lower_content = full_content.lower()
            
            for item_name, item_config in TARGET_ITEMS.items():
                for keyword in item_config['keywords']:
                    if keyword.lower() in lower_content:
                        found_items.append(item_name)
                        logger.info(f"✅ НАЙДЕНО: {item_config['display_name']}")
                        break
            
            current_time = datetime.now().strftime('%H:%M:%S')
            safe_content = html.escape(full_content[:1500])
            
            if found_items:
                # Стикеры в канал
                for item_name in found_items:
                    item_config = TARGET_ITEMS[item_name]
                    self.found_items_count[item_name] += 1
                    
                    if item_config['sticker_id']:
                        logger.info(f"🎨 Отправляю стикер для {item_config['display_name']}")
                        send_telegram_sticker(STOCKS_TELEGRAM_CHANNEL, item_config['sticker_id'])
                
                found_items_list = "\n".join([f"• {TARGET_ITEMS[name]['emoji']} {TARGET_ITEMS[name]['display_name']}" for name in found_items])
                
                bot_message = (
                    f"🎯 <b>Найдены предметы в {current_time}</b>\n"
                    f"{found_items_list}\n\n"
                    f"📋 <b>Сток:</b>\n"
                    f"<pre>{safe_content}</pre>"
                )
            else:
                bot_message = (
                    f"📊 <b>Сток в {current_time}</b>\n"
                    f"🎯 Целевые предметы: не найдены\n\n"
                    f"📋 <b>Сток:</b>\n"
                    f"<pre>{safe_content}</pre>"
                )
            
            # Отправляем
            send_telegram(TELEGRAM_BOT_CHAT_ID, bot_message)
            logger.info(f"✅ Сообщение {message.id} обработано")
            
        except Exception as e:
            logger.error(f"💥 Ошибка обработки: {e}")
            await self.handle_error(f"Ошибка обработки: {e}")

# ==================== ЗАПУСК ====================
async def main():
    USER_TOKEN = os.getenv('USER_TOKEN')
    if not USER_TOKEN:
        logger.error("❌ USER_TOKEN не найден")
        return
    
    bot = SelfBot()
    
    try:
        await bot.start(USER_TOKEN)
    except discord.LoginFailure:
        logger.error("❌ Ошибка входа - неверный токен или аккаунт заблокирован")
        send_telegram(TELEGRAM_BOT_CHAT_ID, "🚨 <b>Аккаунт Discord заблокирован!</b>\nТребуется новый токен.")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
