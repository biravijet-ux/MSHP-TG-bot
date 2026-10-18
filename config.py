import os

from dotenv import load_dotenv

load_dotenv()

VERSION = "1.0.0"

BOT_TOKEN = os.getenv("BOT_TOKEN")

# username канала без @, например mshp_channel
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").replace("@", "")

# id канала, нужен если у канала нет username (например -1001234567890)
CHANNEL_ID = os.getenv("CHANNEL_ID", "")

# id админов через запятую
ADMIN_IDS = []
for admin_id in os.getenv("ADMIN_IDS", "").split(","):
    if admin_id.strip().isdigit():
        ADMIN_IDS.append(int(admin_id))

DB_PATH = os.getenv("DB_PATH", "bot.db")

# ИИ для умного поиска. Если ключа нет - ИИ выключен, обычный поиск работает.
# AI_PROVIDER: "anthropic" (Claude) или "openai" (любой сервис, который работает
# с библиотекой openai: OpenAI, OpenRouter, DeepSeek, локальная Ollama и т.д.)
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic").strip().lower()
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "")
if AI_MODEL == "" and AI_PROVIDER == "anthropic":
    AI_MODEL = "claude-opus-5-5"

# адрес сервиса, только для AI_PROVIDER=openai. Пусто - сам OpenAI
AI_BASE_URL = os.getenv("AI_BASE_URL", "")

# сколько вопросов ИИ можно задать за день на всех (чтобы не потратить все деньги)
AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "100"))
