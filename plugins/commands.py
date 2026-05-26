from pyrogram import Client, filters
from pyrogram.types import Message
from memory.sqlite_memory import add_chat_to_list, remove_chat_from_list, get_dynamic_list
from database.db import get_db
from utils.logger import logger
import config

@Client.on_message(filters.me & filters.command("whitelist", prefixes="."))
async def cmd_whitelist(client: Client, message: Message):
    chat_id = message.chat.id
    # Check if a specific chat ID was passed as argument
    if len(message.command) > 1:
        try:
            chat_id = int(message.command[1])
        except ValueError:
            await message.edit_text("❌ Invalid Chat ID. Must be an integer.")
            return

    await add_chat_to_list(chat_id, "whitelist")
    # Also remove from blacklist if it was there
    await remove_chat_from_list(chat_id)
    
    logger.info(f"Chat {chat_id} added to Whitelist dynamically.")
    await message.edit_text(f"✅ Chat **{chat_id}** has been added to the AI Whitelist.")

@Client.on_message(filters.me & filters.command("blacklist", prefixes="."))
async def cmd_blacklist(client: Client, message: Message):
    chat_id = message.chat.id
    if len(message.command) > 1:
        try:
            chat_id = int(message.command[1])
        except ValueError:
            await message.edit_text("❌ Invalid Chat ID. Must be an integer.")
            return

    await add_chat_to_list(chat_id, "blacklist")
    await remove_chat_from_list(chat_id)  # Remove from whitelist table if it was there
    
    logger.info(f"Chat {chat_id} added to Blacklist dynamically.")
    await message.edit_text(f"✅ Chat **{chat_id}** has been added to the AI Blacklist.")

@Client.on_message(filters.me & filters.command("personality", prefixes="."))
async def cmd_personality(client: Client, message: Message):
    if len(message.command) == 1:
        # Show current personality prompt
        await message.edit_text(
            f"ℹ️ **Current Active Personality:**\n\n`{config.PERSONALITY_PROMPT}`"
        )
        return
        
    # Set new personality
    new_personality = message.text.split(None, 1)[1]
    config.PERSONALITY_PROMPT = new_personality
    logger.info("AI Personality prompt updated by user.")
    await message.edit_text("✅ **AI Personality Prompt updated successfully!**")

@Client.on_message(filters.me & filters.command("clear_memory", prefixes="."))
async def cmd_clear_memory(client: Client, message: Message):
    chat_id = message.chat.id
    async with await get_db() as db:
        await db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM chat_styles WHERE chat_id = ?", (chat_id,))
        await db.commit()
        
    logger.info(f"Memory cleared for chat {chat_id}.")
    await message.edit_text("🧹 **Chat memory and speaking style history cleared!**")
