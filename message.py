import requests, os
from dotenv import load_dotenv

# Завантаження змінних із .env файлу
load_dotenv()

# Отримання значень змінних
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_to_telegram(message):
    """Проста функція для надсилання повідомлення в Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
        print(f"Надсилання в Telegram: {message}")
    except requests.RequestException as e:
        print(f"Помилка надсилання в Telegram: {e}")
