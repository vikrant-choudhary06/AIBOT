import sys
import asyncio
from pyrogram import Client
from utils.logger import logger
import config
from database.db import init_db
from services.ollama import verify_ollama_model
from plugins.chat import init_self_user

async def start_bot():
    """
    Main runner for the AI Telegram Userbot.
    Runs validations, establishes database tables, connects to Pyrogram, and starts listening.
    """
    logger.info("Starting AI Telegram Userbot...")
    
    # 1. Validate .env configurations
    try:
        config.validate_config()
        logger.info("Configuration validation successful.")
    except ValueError as val_err:
        logger.critical(f"Configuration error: {val_err}")
        sys.exit(1)

    # 2. Initialize database
    try:
        await init_db()
    except Exception as db_err:
        logger.critical(f"Failed to initialize SQLite database: {db_err}")
        sys.exit(1)

    # 3. Verify Ollama Connection and Model Presence
    ollama_ok = await verify_ollama_model()
    if not ollama_ok:
        logger.critical(
            "Ollama verification failed. Please make sure Ollama is running and "
            f"the model '{config.MODEL_NAME}' is pulled ('ollama pull {config.MODEL_NAME}')."
        )
        sys.exit(1)

    # 4. Initialize Pyrogram Client
    # Loads Pyrogram plugins automatically from the 'plugins' directory
    app = Client(
        name="ai_userbot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        session_string=config.SESSION_STRING,
        plugins=dict(root="plugins")
    )

    logger.info("Connecting Pyrogram client...")
    try:
        await app.start()
    except Exception as pg_err:
        logger.critical(f"Failed to start Pyrogram client: {pg_err}")
        logger.critical("Check if your API_ID, API_HASH, or SESSION_STRING is correct.")
        sys.exit(1)

    # 5. Initialize Self User ID and Username for dynamic filters
    try:
        await init_self_user(app)
    except Exception as self_err:
        logger.error(f"Could not retrieve self-user identity: {self_err}")

    logger.info("AI Telegram Userbot is now online and listening for messages.")
    
    # Keep the app running until terminated
    try:
        # idle() blocks the execution until SIGINT or SIGTERM is received
        from pyrogram import idle
        await idle()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received.")
    finally:
        logger.info("Disconnecting Pyrogram client...")
        await app.stop()
        logger.info("Userbot offline. Goodbye!")

if __name__ == "__main__":
    # Configure event loops for different OS environments
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Application closed by user.")
