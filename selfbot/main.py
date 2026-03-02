#!/usr/bin/env python3
"""
Резервный селф-бот для мониторинга стока (исправленная версия с Dawn)
"""

import discord
import os
import asyncio
import requests
import random
from datetime import datetime
import logging
import html
import re

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Telegram функции
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID')
STOCKS_TELEGRAM_CHANNEL = os.getenv('STOCKS_TELEGRAM_CHANNEL')

def send_telegram(chat_id, text, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            logger.info(f"✅ Telegram отправлено")
            return True
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

# Твои целевые предметы
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

def extract_full_content(message):
    """Извлекает весь текст из сообщения Discord"""
    full_content = ""
    
    if message.content:
        full_content += f"{message.content}\n\n"
    
    if message.embeds:
        for embed in message.embeds:
            if embed.title:
                full_content += f"{embed.title}\n"
            if embed.description:
                full_content += f"{embed.description}\n"
            if embed.fields:
                for field in embed.fields:
                    full_content += f"\n{field.name}\n{field.value}\n"
            if embed.footer and embed.footer.text:
                full_content += f"\n{embed.footer.text}\n"
    
    full_content = re.sub(r'<:[^:]+:\d+>', '', full_content)
    full_content = re.sub(r'\*\*', '', full_content)
    full_content = html.escape(full_content)
    full_content = '\n'.join([line.strip() for line in full_content.split('\n') if line.strip()])
    
    return full_content.strip()

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
                
                # Получаем последние 3 сообщения (исправленный синтаксис)
                messages = [msg async for msg in channel.history(limit=3)]
                
                for message in messages:
                    if message.id in self.processed_messages:
                        continue
                    
                    # 🔴 ИСПРАВЛЕНО: теперь ищем Dawn, а не Kiro
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
            
            found_items = []
            lower_content = full_content.lower()
            
            for item_name, item_config in TARGET_ITEMS.items():
                for keyword in item_config['keywords']:
                    if keyword.lower() in lower_content:
                        found_items.append(item_name)
                        logger.info(f"🎯 Найдено: {item_config['display_name']}")
                        break
            
            current_time = datetime.now().strftime('%H:%M:%S')
            
            if found_items:
                for item_name in found_items:
                    item_config = TARGET_ITEMS[item_name]
                    self.found_items_count[item_name] += 1
                    
                    if item_config['sticker_id']:
                        send_telegram_sticker(STOCKS_TELEGRAM_CHANNEL, item_config['sticker_id'])
                
                found_items_list = "\n".join([f"• {TARGET_ITEMS[name]['emoji']} {TARGET_ITEMS[name]['display_name']}" for name in found_items])
                
                bot_message = (
                    f"🎯 <b>Найдены предметы в {current_time}:</b>\n"
                    f"{found_items_list}\n\n"
                    f"📋 <b>Сток:</b>\n"
                    f"<pre>{full_content[:3000]}</pre>\n\n"
                    f"#сток"
                )
                send_telegram(TELEGRAM_BOT_CHAT_ID, bot_message)
            else:
                # Можно закомментировать, если не хочешь получать пустые уведомления
                bot_message = (
                    f"📊 <b>Сток в {current_time}</b>\n"
                    f"🎯 Целевые предметы: не найдены\n\n"
                    f"📋 <b>Сток:</b>\n"
                    f"<pre>{full_content[:3000]}</pre>"
                )
                send_telegram(TELEGRAM_BOT_CHAT_ID, bot_message)
                
        except Exception as e:
            logger.error(f"💥 Ошибка обработки: {e}")

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
