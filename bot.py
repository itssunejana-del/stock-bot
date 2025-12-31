import requests
import os
import time
import json
from datetime import datetime

def print_header(text):
    print("\n" + "="*60)
    print(f" {text}")
    print("="*60)

def test_channel_access(channel_id, channel_name, token):
    """Тестирует доступ бота к конкретному каналу"""
    print(f"\n🔍 Проверяю доступ к каналу: {channel_name}")
    print(f"   ID канала: {channel_id}")
    
    url = f"https://discord.com/api/v10/channels/{channel_id}"
    headers = {"Authorization": f"Bot {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            channel_data = response.json()
            print(f"   ✅ УСПЕХ: Бот имеет доступ к каналу!")
            print(f"   📝 Название канала: {channel_data.get('name', 'неизвестно')}")
            print(f"   🏷️  Тип: {'текстовый' if channel_data.get('type') == 0 else 'голосовой/другой'}")
            print(f"   🔒 NSFW: {'Да' if channel_data.get('nsfw', False) else 'Нет'}")
            return True, channel_data
            
        elif response.status_code == 403:
            print(f"   ❌ ОШИБКА 403: НЕТ ДОСТУПА")
            print(f"   📌 Возможные причины:")
            print(f"      • Бот не добавлен на сервер")
            print(f"      • У бота нет прав на просмотр канала")
            print(f"      • Канал приватный и бот не добавлен")
            return False, None
            
        elif response.status_code == 404:
            print(f"   ❌ ОШИБКА 404: КАНАЛ НЕ НАЙДЕН")
            print(f"   📌 Возможные причины:")
            print(f"      • Неверный ID канала")
            print(f"      • Бот не на том сервере")
            print(f"      • Канал был удалён")
            return False, None
            
        else:
            print(f"   ⚠️  ОШИБКА {response.status_code}: {response.text[:100]}")
            return False, None
            
    except requests.exceptions.Timeout:
        print(f"   ⏰ ТАЙМАУТ: Discord не отвечает")
        return False, None
    except Exception as e:
        print(f"   💥 ОШИБКА: {e}")
        return False, None

def test_message_reading(channel_id, channel_name, token):
    """Тестирует возможность чтения сообщений в канале"""
    print(f"\n📖 Проверяю чтение сообщений в: {channel_name}")
    
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=2"
    headers = {"Authorization": f"Bot {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            messages = response.json()
            print(f"   ✅ УСПЕХ: Может читать сообщения!")
            print(f"   📊 Найдено сообщений: {len(messages)}")
            
            if messages:
                latest_msg = messages[0]
                author = latest_msg.get('author', {})
                print(f"   🕐 Последнее сообщение: {author.get('username', 'неизвестно')}")
                print(f"   📝 Текст: {latest_msg.get('content', 'нет текста')[:50]}...")
                
                # Проверяем, есть ли сообщения от Kiro
                for msg in messages:
                    author_name = msg.get('author', {}).get('username', '').lower()
                    if 'kiro' in author_name:
                        print(f"   🎯 НАЙДЕНО: Сообщение от Kiro!")
                        return True, messages
            return True, messages
            
        elif response.status_code == 403:
            print(f"   ❌ ОШИБКА 403: Нет прав на чтение сообщений")
            return False, None
            
        elif response.status_code == 404:
            print(f"   ❌ ОШИБКА 404: Канал не найден")
            return False, None
            
        else:
            print(f"   ⚠️  ОШИБКА {response.status_code}")
            return False, None
            
    except Exception as e:
        print(f"   💥 ОШИБКА: {e}")
        return False, None

def test_bot_info(token):
    """Получает информацию о боте"""
    print_header("🤖 ИНФОРМАЦИЯ О БОТЕ")
    
    url = "https://discord.com/api/v10/users/@me"
    headers = {"Authorization": f"Bot {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            bot_data = response.json()
            print(f"✅ Бот авторизован!")
            print(f"   👤 Имя: {bot_data.get('username')}#{bot_data.get('discriminator')}")
            print(f"   🆔 ID: {bot_data.get('id')}")
            print(f"   🤖 Бот: {'Да' if bot_data.get('bot', False) else 'Нет'}")
            return True, bot_data
        else:
            print(f"❌ Ошибка получения информации: {response.status_code}")
            return False, None
    except Exception as e:
        print(f"💥 Ошибка: {e}")
        return False, None

def test_rate_limits(token):
    """Тестирует лимиты запросов"""
    print_header("⏱️ ТЕСТ ЛИМИТОВ DISCORD")
    
    # Делаем несколько быстрых запросов
    test_channel = "123456789012345678"  # Фейковый ID для теста лимитов
    
    for i in range(3):
        print(f"\n📤 Запрос #{i+1}...")
        url = f"https://discord.com/api/v10/channels/{test_channel}"
        headers = {"Authorization": f"Bot {token}"}
        
        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, timeout=5)
            end_time = time.time()
            
            response_time = (end_time - start_time) * 1000
            
            if response.status_code == 404:  # Ожидаем 404 для фейкового канала
                print(f"   ✅ Ответ за {response_time:.0f} мс: 404 (ожидаемо)")
            elif response.status_code == 429:
                retry_after = response.json().get('retry_after', 0)
                print(f"   ⚠️  ЛИМИТ: {response.status_code}, ждать {retry_after} сек")
                print(f"   ⏳ Discord лимитирует запросы!")
                return True
            else:
                print(f"   📊 Ответ за {response_time:.0f} мс: {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"   ⏰ Таймаут запроса #{i+1}")
        except Exception as e:
            print(f"   💥 Ошибка: {e}")
    
    print("\n✅ Лимиты Discord в норме")
    return False

def main():
    print_header("🔧 ТЕСТ ДОСТУПА DISCORD БОТА")
    print("Проверяем, что новый бот имеет доступ ко всем каналам Kiro")
    
    # Загружаем переменные окружения
    print("\n📋 ЗАГРУЖАЮ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ...")
    
    # Получаем токен из переменных окружения
    token = os.getenv('DISCORD_TOKEN')
    
    if not token:
        print("❌ ОШИБКА: Переменная DISCORD_TOKEN не установлена!")
        print("📌 Как установить:")
        print("   1. В Render.com: Environment → Add Environment Variable")
        print("   2. Локально: export DISCORD_TOKEN='твой_токен'")
        print("\nТокен должен выглядеть так: MTIwOTU2NDA0NDcxNDQ1NTY4OA.G1Uy8n...")
        return
    
    print(f"✅ Токен загружен (первые 10 символов): {token[:10]}...")
    
    # Получаем ID каналов
    channels = {
        "🌱 Семена": os.getenv('SEEDS_CHANNEL_ID'),
        "🎫 Пасс-шоп": os.getenv('PASS_SHOP_CHANNEL_ID'),
        "🎪 Ивент-шоп": os.getenv('EVENT_SHOP_CHANNEL_ID')
    }
    
    print("\n📊 ЗАГРУЖЕННЫЕ КАНАЛЫ:")
    for name, channel_id in channels.items():
        if channel_id:
            print(f"   {name}: {channel_id}")
        else:
            print(f"   ⚠️  {name}: НЕ УСТАНОВЛЕН")
    
    # Тестируем информацию о боте
    bot_ok, bot_info = test_bot_info(token)
    if not bot_ok:
        print("\n❌ БОТ НЕ АВТОРИЗОВАН! Проверь токен.")
        return
    
    # Тестируем доступ к каждому каналу
    print_header("📡 ПРОВЕРКА ДОСТУПА К КАНАЛАМ")
    
    results = {}
    kiro_found = False
    
    for channel_name, channel_id in channels.items():
        if not channel_id:
            print(f"\n⚠️  {channel_name}: ID не указан, пропускаю")
            results[channel_name] = "NO_ID"
            continue
        
        # Тест 1: Доступ к каналу
        access_ok, channel_data = test_channel_access(channel_id, channel_name, token)
        
        if access_ok:
            # Тест 2: Чтение сообщений
            read_ok, messages = test_message_reading(channel_id, channel_name, token)
            
            if read_ok and messages:
                # Проверяем сообщения от Kiro
                for msg in messages:
                    author = msg.get('author', {})
                    if 'kiro' in author.get('username', '').lower():
                        kiro_found = True
                        print(f"   🎯 ВАЖНО: В канале {channel_name} есть сообщения от Kiro!")
                        break
            
            results[channel_name] = "OK" if read_ok else "NO_READ"
        else:
            results[channel_name] = "NO_ACCESS"
    
    # Тестируем лимиты Discord
    print_header("📊 ИТОГИ ПРОВЕРКИ")
    
    print("\n🎯 РЕЗУЛЬТАТЫ ПО КАНАЛАМ:")
    for channel_name, result in results.items():
        if result == "OK":
            print(f"   ✅ {channel_name}: Полный доступ и чтение")
        elif result == "NO_READ":
            print(f"   ⚠️  {channel_name}: Доступ есть, но нельзя читать")
        elif result == "NO_ACCESS":
            print(f"   ❌ {channel_name}: Нет доступа к каналу")
        elif result == "NO_ID":
            print(f"   📝 {channel_name}: ID не указан")
    
    if kiro_found:
        print("\n🎯 ОТЛИЧНО: Бот может читать сообщения Kiro!")
    else:
        print("\n⚠️  ВНИМАНИЕ: Не найдено сообщений от Kiro в последних сообщениях")
        print("   Это нормально если Kiro давно не постил")
    
    # Тестируем лимиты
    has_rate_limit = test_rate_limits(token)
    
    if has_rate_limit:
        print("\n🚨 ВНИМАНИЕ: Discord лимитирует запросы!")
        print("   Нужно увеличить интервалы между запросами")
    
    print_header("🎯 РЕКОМЕНДАЦИИ")
    
    # Анализируем результаты
    all_ok = all(r == "OK" for r in results.values() if r != "NO_ID")
    
    if all_ok:
        print("✅ ВСЕ КАНАЛЫ ДОСТУПНЫ! Можно запускать мониторинг.")
        print("\n🎯 Дальнейшие шаги:")
        print("   1. Запустить мониторинг с интервалом 30 секунд")
        print("   2. Следить за логами на ошибки 429")
        print("   3. Если появятся ошибки - увеличить интервалы")
    else:
        print("⚠️  ЕСТЬ ПРОБЛЕМЫ С ДОСТУПОМ!")
        print("\n🔧 Что делать:")
        
        if any(r == "NO_ACCESS" for r in results.values()):
            print("   1. Проверить что бот добавлен на сервер")
            print("   2. Проверить права бота на каналах")
            print("   3. Создать новую invite-ссылку с правами:")
            print("      • View Channels")
            print("      • Read Messages")
            print("      • Read Message History")
        
        if any(r == "NO_READ" for r in results.values()):
            print("   1. Проверить настройки приватности каналов")
            print("   2. Убедиться что бот добавлен в приватные каналы")
        
        if any(r == "NO_ID" for r in results.values()):
            print("   1. Установить ID недостающих каналов")
            print("   2. Включить режим разработчика в Discord")
            print("   3. Правой кнопкой по каналу → Копировать ID")
    
    print("\n📅 Время проверки:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

if __name__ == "__main__":
    main()
