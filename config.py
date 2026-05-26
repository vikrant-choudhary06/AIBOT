import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Logs and DB directories
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

DB_DIR = BASE_DIR / "database"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "userbot.db"

# Telegram Credentials
API_ID_RAW = os.getenv("API_ID")
API_ID = int(API_ID_RAW) if API_ID_RAW else None
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

# Ollama AI Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL_NAME = os.getenv("MODEL_NAME", "gemma:2b")

# Helper to parse list of chat IDs
def _parse_chat_ids(env_val: str) -> set[int]:
    if not env_val:
        return set()
    result = set()
    for item in env_val.split(","):
        item = item.strip()
        if item:
            try:
                result.add(int(item))
            except ValueError:
                # Support usernames or non-numeric items if needed, but standard is numeric ID
                pass
    return result

# Chat Whitelists and Blacklists
WHITELIST_CHATS = _parse_chat_ids(os.getenv("WHITELIST_CHATS", ""))
BLACKLIST_CHATS = _parse_chat_ids(os.getenv("BLACKLIST_CHATS", ""))

# Cooldown and Rate Limiting
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "5"))
REPLY_CHANCE_GROUP = float(os.getenv("REPLY_CHANCE_GROUP", "0.05"))

# AI Personality Prompt
DEFAULT_PERSONALITY = (
    "You are a casual human chatter named Amit. You talk to friends on Telegram. "
    "You MUST ALWAYS speak in Hinglish (Hindi written using the English alphabet) like "
    "'kya chal raha hai?', 'kuch nhi yaar', 'bas badiya tum batao', 'ha ha sahi hai'. "
    "Keep replies very short, realistic, casual, and human-like (usually 1-2 sentences). "
    "Do NOT act like an AI, virtual assistant, or robot. Use normal emojis occasionally. "
    "If someone roasts you, roast them back casually. Never start replies with formal greetings or introductory phrases."
)
PERSONALITY_PROMPT = os.getenv("PERSONALITY_PROMPT", DEFAULT_PERSONALITY)

# Simple validation check
def validate_config():
    missing = []
    if not API_ID:
        missing.append("API_ID")
    if not API_HASH:
        missing.append("API_HASH")
    if not SESSION_STRING:
        missing.append("SESSION_STRING")
    
    if missing:
        raise ValueError(f"Missing required configuration variables in .env: {', '.join(missing)}")
