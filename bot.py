import requests
import os

# Проверка что новый бот работает
def test_new_bot():
    token = os.getenv('DISCORD_TOKEN_NEW')
    channel_id = os.getenv('SEEDS_CHANNEL_ID')
    
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=1"
    headers = {"Authorization": f"Bot {token}"}
    
    response = requests.get(url, headers=headers, timeout=10)
    
    if response.status_code == 200:
        print("✅ Новый бот работает отлично!")
        return True
    else:
        print(f"❌ Ошибка: {response.status_code}")
        return False
