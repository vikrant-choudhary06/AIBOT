import aiosqlite
from config import DB_PATH
from utils.logger import logger

async def get_db():
    """
    Returns an async connection to the SQLite database.
    """
    db = await aiosqlite.connect(DB_PATH)
    # Enable WAL mode for better concurrency and foreign keys
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    return db

async def init_db():
    """
    Creates tables if they do not exist.
    """
    logger.info("Initializing SQLite database...")
    async with await get_db() as db:
        # Create messages table for context memory
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                sender_name TEXT,
                text TEXT,
                timestamp INTEGER NOT NULL,
                is_ai INTEGER DEFAULT 0
            )
        """)
        
        # Create index on chat_id and timestamp for faster context queries
        await db.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_time ON messages (chat_id, timestamp)")

        # Create chat styles table (stores learned style details in JSON)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_styles (
                chat_id INTEGER PRIMARY KEY,
                style_data TEXT NOT NULL
            )
        """)

        # Create user profiles table for per-user summaries
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                summary TEXT NOT NULL,
                last_seen INTEGER NOT NULL
            )
        """)

        # Create group profiles table for per-group context summaries
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_profiles (
                chat_id INTEGER PRIMARY KEY,
                summary TEXT NOT NULL,
                last_seen INTEGER NOT NULL
            )
        """)

        # Create cooldowns table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cooldowns (
                chat_id INTEGER PRIMARY KEY,
                last_reply_time REAL NOT NULL
            )
        """)

        # Create whitelists/blacklists table for dynamic runtime changes
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whitelists (
                chat_id INTEGER PRIMARY KEY,
                list_type TEXT NOT NULL CHECK(list_type IN ('whitelist', 'blacklist'))
            )
        """)

        await db.commit()
    logger.info("Database initialization complete.")
