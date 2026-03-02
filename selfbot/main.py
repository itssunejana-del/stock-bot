#!/usr/bin/env python3
"""
Резервный селф-бот для мониторинга стока (полная версия с ролями)
С исправленными Telegram функциями из старого кода
"""

import discord
import os
import asyncio
import requests
import random
import time  # Добавлено для обработки 429 ошибок
from datetime import datetime
import logging
import html
import re

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
# ID ролей Discord → названия предметов
ROLE_NAMES = {
    '1477643077882609755': 'Mango',      # 🥭 Mango
    '1477643000073949214': 'Bamboo',     # 🎋 Bamboo
    '1442312884859179049': 'Cabbage',    # 🥬 Cabbage
    '1426610862591840266': 'Cherry',     # 🍒 Cherry
    '1439345675690049666': 'Carrot',     # 🥕 Carrot (для проверки)
}

# ==================== ЦЕЛЕВЫЕ ПРЕДМЕТЫ ====================
# Только для этих предметов будут стикеры и отметка "Найдено"
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

# ==================== TELEGRAM ФУНКЦИИ (из старого кода) ====================
def send_telegram(chat_id, text, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Telegram отправлено в {chat_id}")
            return True
        elif response.status_code == 429:
            retry_after = response.json().get('parameters', {}).get('retry_after', 30)
            logger.warning(f"⚠️ Лимит Telegram, жду {retry_after} сек")
            time.sleep(retry_after)
            return False
        else:
            logger.error(f"❌ Telegram ошибка {response.status_code}: {response.text[:100]}")
            return False
    except Exception as e:
        logger.error(f'❌ Telegram error: {e}')
        return False

def send_to_bot(text):
    """Отправляет сообщение в личку бота"""
    if TELEGRAM_BOT_CHAT_ID:
        return send_telegram(TELEGRAM_BOT_CHAT_ID, text)
    return False

def send_telegram_sticker(chat_id, sticker_id):
    """Отправляет стикер в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendSticker"
        data = {"chat_id": chat_id, "sticker": sticker_id}
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            logger.info(f"📢 Стикер отправлен в канал")
            return True
        else:
            logger.error(f"❌ Ошибка отправки стикера: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f'❌ Ошибка отправки стикера: {e}')
        return False

# ==================== ФУНКЦИЯ ИЗВЛЕЧЕНИЯ ТЕКСТА ====================
def extract_full_content(message):
    """Извлекает весь текст из сообщения Discord и заменяет роли на названия"""
    full_content = ""
    
    # Обрабатываем основной текст сообщения
    if message.content:
        content = message.content
        # Заменяем упоминания ролей на названия
        for role_id, role_name in ROLE_NAMES.items():
            content = content.replace(f'<@&{role_id}>', role_name)
        full_content += f"{content}\n\n"
    
    # Обрабатываем эмбеды
    if message.embeds:
        for embed in message.embeds:
            if embed.title:
                full_content += f"{embed.title}\n"
            if embed.description:
                # Тоже заменяем роли в описании эмбеда
                desc = embed.description
                for role_id, role_name in ROLE_NAMES.items():
                    desc = desc.replace(f'<@&{role_id}>', role_name)
                full_content += f"{desc}\n"
            if embed.fields:
                for field in embed.fields:
                    full_content += f"\n{field.name}\n{field.value}\n"
            if embed.footer and embed.footer.text:
                full_content += f"\n{embed.footer.text}\n"
    
    # Очистка от лишнего
    full_content = re.sub(r'<:[^:]+:\d+>', '', full_content)
    full_content = re.sub(r'\*\*', '', full_content)
    full_content = html.escape(full_content)
    full_content = '\n'.join([line.strip() for line in full_content.split('\n') if line.strip()])
    
    return full_content.strip()

# ==================== ОСНОВНОЙ КЛАСС БОТА ====================
class SelfBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processed_messages = set()
        self.found_items_count = {name: 0 for name in TARGET_ITEMS.keys()}
        self.channel_id = int(os.getenv('STOCKS_CHANNEL_ID'))
        self.max_cache_size = 50
        
    async def on_ready(self):
        logger.info(f'✅ Резервный селф-бот {self.user} запущен!')
        self.loop.create_task(self.poll_channel())
    
    async def poll_channel(self):
        """Опрос канала каждые 25-35 секунд"""
        await self.wait_until_ready()
        
        while not self.is_closed():
            try:
                channel = self.get_channel(self.channel_id)
                if not channel:
                    logger.error(f"❌ Канал {self.channel_id} не найден")
                    await asyncio.sleep(60)
                    continue
                
                # Получаем последние 3 сообщения
                messages = [msg async for msg in channel.history(limit=3)]
                
                for message in messages:
                    if message.id in self.processed_messages:
                        continue
                    
                    # Проверяем автора (бот Dawn)
                    if 'dawn' not in message.author.name.lower():
                        continue
                    
                    logger.info(f"📨 Сообщение от Dawn (ID: {message.id})")
                    await self.process_stock_message(message)
                    
                    self.processed_messages.add(message.id)
                    if len(self.processed_messages) > self.max_cache_size:
                        self.processed_messages.pop()
                
                # Случайная задержка 25-35 секунд
                delay = random.uniform(25, 35)
                logger.info(f"💤 Следующая проверка через {delay:.1f} сек")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в poll_channel: {e}")
                await asyncio.sleep(60)
    
    async def process_stock_message(self, message):
        """Обработка сообщения со стоком"""
        try:
            full_content = extract_full_content(message)
            if not full_content:
                return
            
            # Поиск целевых предметов
            found_items = []
            lower_content = full_content.lower()
            
            for item_name, item_config in TARGET_ITEMS.items():
                for keyword in item_config['keywords']:
                    if keyword.lower() in lower_content:
                        found_items.append(item_name)
                        logger.info(f"🎯 Найдено: {item_config['display_name']}")
                        break
            
            current_time = datetime.now().strftime('%H:%M:%S')
            
            # Отправка в Telegram
            if found_items:
                # Стикеры в канал (только для найденных предметов)
                for item_name in found_items:
                    item_config = TARGET_ITEMS[item_name]
                    self.found_items_count[item_name] += 1
                    
                    if item_config['sticker_id']:
                        send_telegram_sticker(STOCKS_TELEGRAM_CHANNEL, item_config['sticker_id'])
                
                # Текстовое уведомление в личку бота (со всем стоком)
                found_items_list = "\n".join([f"• {TARGET_ITEMS[name]['emoji']} {TARGET_ITEMS[name]['display_name']}" for name in found_items])
                
                # Экранируем HTML в содержимом
                safe_content = html.escape(full_content[:3000])
                
                bot_message = (
                    f"🎯 <b>Найдены предметы в {current_time}:</b>\n"
                    f"{found_items_list}\n\n"
                    f"📋 <b>Полный сток:</b>\n"
                    f"<pre>{safe_content}</pre>\n\n"
                    f"#сток"
                )
                send_telegram(TELEGRAM_BOT_CHAT_ID, bot_message)
            else:
                # Информационное сообщение в личку бота (когда нет целевых предметов)
                safe_content = html.escape(full_content[:3000])
                
                bot_message = (
                    f"📊 <b>Сток в {current_time}</b>\n"
                    f"🎯 Целевые предметы: не найдены\n\n"
                    f"📋 <b>Полный сток:</b>\n"
                    f"<pre>{safe_content}</pre>"
                )
                send_telegram(TELEGRAM_BOT_CHAT_ID, bot_message)
                
        except Exception as e:
            logger.error(f"💥 Ошибка обработки: {e}")

# ==================== ЗАПУСК ====================
async def main():
    USER_TOKEN = os.getenv('USER_TOKEN')
    if not USER_TOKEN:
        logger.error("❌ USER_TOKEN не найден")
        return
    
    bot = SelfBot()
    try:
        await bot.start(USER_TOKEN)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
