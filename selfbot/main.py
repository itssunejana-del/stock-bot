#!/usr/bin/env python3
"""
Резервный селф-бот для мониторинга стока
С принудительной отправкой ссылок на все сообщения
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
ROLE_NAMES = {
    '1426610862591840266': 'Cherry',
    '1442312884859179049': 'Cabbage',
    '1477643000073949214': 'Bamboo',
    '1477643077882609755': 'Mango',
    '1439345675690049666': 'Carrot',
    '1392620784870101002': 'Mushroom',
    '1392622053278093473': 'Onion',
    '1392622157460144198': 'Corn',
}

# ==================== ЦЕЛЕВЫЕ ПРЕДМЕТЫ ====================
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

# ==================== ФУНКЦИЯ ИЗВЛЕЧЕНИЯ ТЕКСТА ====================
def extract_full_content(message):
    """Извлекает текст из сообщения"""
    full_content = ""
    
    # Эмбеды
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
    
    # Обычный текст
    if message.content:
        content = message.content
        for role_id, role_name in ROLE_NAMES.items():
            content = content.replace(f'<@&{role_id}>', role_name)
        full_content += f"{content}\n"
    
    # Кнопки
    if hasattr(message, 'components') and message.components:
        for component in message.components:
            if hasattr(component, 'children'):
                for child in component.children:
                    if hasattr(child, 'label') and child.label:
                        full_content += f"[{child.label}]\n"
    
    # Очистка
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
        
        current_time = datetime.now().strftime('%H:%M:%S')
        test_message = (
            f"🤖 <b>Бот запущен!</b>\n"
            f"⏰ Время: {current_time}\n"
            f"📊 Статус: ✅ Подключен к Discord\n"
            f"📡 Канал: {self.channel_id}\n"
            f"💾 В памяти: {len(self.processed_messages)} сообщений\n\n"
            f"🔍 Отслеживаю: 🍒 🥬 🎋 🥭\n\n"
            f"📎 На каждое сообщение буду присылать ссылку"
        )
        send_telegram(TELEGRAM_BOT_CHAT_ID, test_message)
        
        self.loop.create_task(self.auto_save())
        self.polling_task = self.loop.create_task(self.poll_channel())
    
    async def auto_save(self):
        while not self.is_closed():
            await asyncio.sleep(300)
            state = {'processed_messages': list(self.processed_messages)[-self.max_cache_size:]}
            save_state(state)
            logger.info("💾 Состояние сохранено")
    
    async def poll_channel(self):
        await self.wait_until_ready()
        
        while not self.is_closed():
            try:
                channel = self.get_channel(self.channel_id)
                if not channel:
                    logger.error(f"❌ Канал {self.channel_id} не найден")
                    await asyncio.sleep(60)
                    continue
                
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
                
                delay = random.uniform(25, 35)
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в poll_channel: {e}")
                await asyncio.sleep(60)
    
    async def on_message(self, message):
        try:
            if message.channel.id != self.channel_id:
                return
            
            if 'dawn' not in message.author.name.lower():
                return
            
            if message.id in self.processed_messages:
                logger.info(f"⏭️ Дубль сообщения {message.id}")
                return
            
            logger.info(f"📨 НОВОЕ сообщение от Dawn (ID: {message.id})")
            await self.process_stock_message(message)
            
            self.processed_messages.add(message.id)
            if len(self.processed_messages) > self.max_cache_size:
                self.processed_messages.pop()
            
            state = {'processed_messages': list(self.processed_messages)[-self.max_cache_size:]}
            save_state(state)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в on_message: {e}")
            await self.handle_error(f"Ошибка обработки сообщения: {e}")
    
    async def on_disconnect(self):
        logger.warning("⚠️ Отключение от Discord")
        await self.handle_error("⚠️ Потеря соединения с Discord. Переподключаюсь...")
    
    async def on_error(self, event, *args, **kwargs):
        logger.error(f"❌ Ошибка Discord: {event}")
        await self.handle_error(f"Ошибка Discord: {event}")
    
    async def handle_error(self, error_text):
        now = datetime.now()
        if self.last_error_time and (now - self.last_error_time).seconds < 60:
            return
        
        self.last_error_time = now
        send_telegram(TELEGRAM_BOT_CHAT_ID, f"🚨 <b>ВНИМАНИЕ!</b>\n{error_text}")
    
    async def process_stock_message(self, message):
        try:
            logger.info(f"🔍 Обработка сообщения {message.id}")
            
            # Всегда получаем свежую копию
            try:
                channel = await self.fetch_channel(self.channel_id)
                fresh_message = await channel.fetch_message(message.id)
                logger.info(f"📦 Получил свежую копию сообщения {message.id}")
                message = fresh_message
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить свежую копию: {e}")
            
            # Извлекаем текст
            full_content = extract_full_content(message)
            
            # Формируем ссылку на сообщение
            guild_id = message.guild.id if message.guild else '@me'
            msg_link = f"https://discord.com/channels/{guild_id}/{self.channel_id}/{message.id}"
            
            # ВСЕГДА отправляем ссылку в Telegram
            link_message = f"🔗 <b>Новое сообщение от Dawn</b>\nID: {message.id}\nСсылка: {msg_link}"
            send_telegram(TELEGRAM_BOT_CHAT_ID, link_message)
            
            # Если есть текст - отправляем и его тоже
            if full_content:
                logger.info(f"✅ Текст извлечен: {full_content[:100]}...")
                
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
                
                send_telegram(TELEGRAM_BOT_CHAT_ID, bot_message)
            else:
                logger.warning("❌ Текст не извлечен, отправлена только ссылка")
            
            logger.info(f"✅ Сообщение {message.id} обработано (ссылка отправлена)")
            
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
