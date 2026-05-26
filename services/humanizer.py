import asyncio
import time
import random
from pyrogram import Client
from pyrogram.enums import ChatAction
from database.db import get_db
from config import COOLDOWN_SECONDS, REPLY_CHANCE_GROUP
from utils.logger import logger

# Globally guaranteed basic Telegram reactions to avoid REACTION_INVALID errors
CASUAL_REACTIONS = ["👍", "❤️", "🔥", "😂", "👏"]

class TypingSimulator:
    """
    Context manager to simulate typing on Telegram.
    Runs a background loop that sends the 'typing' action every 4 seconds
    until the context block is exited.
    """
    def __init__(self, client: Client, chat_id: int):
        self.client = client
        self.chat_id = chat_id
        self.task = None

    async def __aenter__(self):
        self.task = asyncio.create_task(self._typing_loop())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def _typing_loop(self):
        try:
            while True:
                await self.client.send_chat_action(self.chat_id, ChatAction.TYPING)
                await asyncio.sleep(4.0)  # Telegram actions expire in ~5 seconds
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Error in typing simulation loop: {e}")

async def check_and_update_cooldown(chat_id: int) -> bool:
    """
    Checks if a cooldown is active for the given chat_id.
    If not active, updates the last reply time and returns False (safe to reply).
    If active, returns True (cooldown active, ignore).
    """
    now = time.time()
    async with get_db() as db:
        async with db.execute("SELECT last_reply_time FROM cooldowns WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            
        if row:
            last_reply = row[0]
            if now - last_reply < COOLDOWN_SECONDS:
                return True
                
        # Update cooldown
        await db.execute(
            "INSERT OR REPLACE INTO cooldowns (chat_id, last_reply_time) VALUES (?, ?)",
            (chat_id, now)
        )
        await db.commit()
    return False

def calculate_reading_delay(message_text: str) -> float:
    """
    Simulates a very brief reading speed to ensure rapid responses.
    """
    if not message_text:
        return 0.1
    # Highly optimized reading delay (0.1 to 0.4 seconds)
    return random.uniform(0.1, 0.4)

def calculate_typing_delay(response_text: str) -> float:
    """
    Simulates a very brief typing completion delay.
    """
    # Highly optimized typing completion delay (0.1 to 0.4 seconds)
    return random.uniform(0.1, 0.4)

def should_randomly_reply(chat_id: int) -> bool:
    """
    Evaluates if the bot should randomly participate in a group message
    based on the configured REPLY_CHANCE_GROUP.
    """
    return random.random() < REPLY_CHANCE_GROUP

def should_react_instead_of_reply() -> tuple[bool, str | None]:
    """
    10% chance to send a casual emoji reaction instead of a written reply.
    Returns (True, emoji) or (False, None).
    """
    if random.random() < 0.10:
        return True, random.choice(CASUAL_REACTIONS)
    return False, None

async def send_reaction_safe(client: Client, chat_id: int, message_id: int, emoji: str) -> bool:
    """
    Sends a reaction to a message, catching potential API restrictions.
    """
    try:
        await client.send_reaction(chat_id, message_id, emoji)
        return True
    except Exception as e:
        logger.debug(f"Failed to send reaction to message {message_id} in {chat_id} (normal if chat has disabled reactions): {e}")
        return False
