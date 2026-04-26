import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
TRIGGER_TOKEN = os.getenv("TRIGGER_TOKEN")

# Safety check: fail loudly if any key is missing
if not all([GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SERPAPI_KEY, DATABASE_URL, TRIGGER_TOKEN]):
    raise ValueError("Missing required environment variables. Check your .env file.")
