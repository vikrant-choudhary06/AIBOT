import json
import time
import re
from collections import Counter
from database.db import get_db
from utils.logger import logger

# Helper to clean and tokenise words for learning
CLEAN_WORD_RE = re.compile(r"\b[a-zA-Z]{3,15}\b")

# Extract emojis
EMOJI_RE = re.compile(r"[\u2600-\u27BF]|[\u1F300-\u1F6FF]|[\u1F900-\u1F9FF]|[\u1F600-\u1F64F]")

async def save_message(chat_id: int, message_id: int, sender_id: int, sender_name: str, text: str, is_ai: bool = False):
    """
    Saves a message in the database.
    """
    is_ai_val = 1 if is_ai else 0
    timestamp = int(time.time())
    
    async with await get_db() as db:
        await db.execute(
            """
            INSERT INTO messages (chat_id, message_id, sender_id, sender_name, text, timestamp, is_ai)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, message_id, sender_id, sender_name, text, timestamp, is_ai_val)
        )
        await db.commit()

async def get_chat_history(chat_id: int, limit: int = 15) -> list[dict]:
    """
    Retrieves the last N messages for a chat formatted as Ollama chat history.
    """
    async with await get_db() as db:
        async with db.execute(
            """
            SELECT sender_name, text, is_ai FROM messages 
            WHERE chat_id = ? 
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (chat_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            
    # Reverse rows to maintain chronological order
    rows.reverse()
    
    history = []
    for sender_name, text, is_ai in rows:
        role = "assistant" if is_ai == 1 else "user"
        # For non-AI messages, prefix content with sender's name to give group context
        content = text if role == "assistant" else f"{sender_name}: {text}"
        history.append({
            "role": role,
            "content": content
        })
    return history

async def get_raw_history_texts(chat_id: int, limit: int = 15) -> list[str]:
    """
    Helper to get raw text of last messages (e.g. for anti-loop verification).
    """
    async with await get_db() as db:
        async with db.execute(
            "SELECT text FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
            (chat_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
    return [row[0] for row in rows]

async def update_chat_style(chat_id: int, text: str):
    """
    Learns speaking style from incoming chat messages.
    Tracks common words, emojis, and average sentence length.
    """
    if not text or len(text.strip()) < 3:
        return

    async with await get_db() as db:
        # Fetch current style data
        async with db.execute("SELECT style_data FROM chat_styles WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        
        style = {
            "common_words": {},
            "common_emojis": {},
            "avg_length": 0.0,
            "message_count": 0
        }
        
        if row:
            try:
                style = json.loads(row[0])
            except Exception:
                pass

        # Update message count
        count = style.get("message_count", 0)
        avg_len = style.get("avg_length", 0.0)
        
        # Calculate new average length
        new_len = len(text)
        new_avg_len = ((avg_len * count) + new_len) / (count + 1)
        style["avg_length"] = round(new_avg_len, 2)
        style["message_count"] = count + 1

        # Words Counter
        words = CLEAN_WORD_RE.findall(text.lower())
        word_freq = style.get("common_words", {})
        for word in words:
            if len(word) > 3:  # ignore short words
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Keep top 30 words to avoid massive JSON sizes
        if len(word_freq) > 100:
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:30]
            style["common_words"] = dict(sorted_words)
        else:
            style["common_words"] = word_freq

        # Emoji Counter
        emojis = EMOJI_RE.findall(text)
        emoji_freq = style.get("common_emojis", {})
        for emoji in emojis:
            emoji_freq[emoji] = emoji_freq.get(emoji, 0) + 1
        
        # Keep top 10 emojis
        if len(emoji_freq) > 30:
            sorted_emojis = sorted(emoji_freq.items(), key=lambda x: x[1], reverse=True)[:10]
            style["common_emojis"] = dict(sorted_emojis)
        else:
            style["common_emojis"] = emoji_freq

        # Save back
        await db.execute(
            "INSERT OR REPLACE INTO chat_styles (chat_id, style_data) VALUES (?, ?)",
            (chat_id, json.dumps(style))
        )
        await db.commit()

async def get_style_summary(chat_id: int) -> str:
    """
    Generates a concise style summary to inject into the system prompt.
    """
    async with await get_db() as db:
        async with db.execute("SELECT style_data FROM chat_styles WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            
    if not row:
        return ""
        
    try:
        style = json.loads(row[0])
        # Find top 5 words and top 3 emojis
        top_words = sorted(style.get("common_words", {}).items(), key=lambda x: x[1], reverse=True)[:5]
        top_emojis = sorted(style.get("common_emojis", {}).items(), key=lambda x: x[1], reverse=True)[:3]
        
        words_str = ", ".join([w[0] for w in top_words])
        emojis_str = "".join([e[0] for e in top_emojis])
        avg_len = style.get("avg_length", 20.0)
        
        summary_parts = []
        if words_str:
            summary_parts.append(f"Often use words/slang: [{words_str}]")
        if emojis_str:
            summary_parts.append(f"Often use emojis: {emojis_str}")
        
        # Adjust length guideline
        if avg_len < 15:
            summary_parts.append("Keep your replies extremely brief.")
        elif avg_len > 80:
            summary_parts.append("You can reply with more detailed sentences.")
            
        return " - " + "; ".join(summary_parts)
    except Exception as e:
        logger.error(f"Error generating style summary for chat {chat_id}: {e}")
        return ""

async def get_profile_summary(profile_id: int, is_group: bool = False) -> str:
    """
    Retrieves summary profile.
    """
    table = "group_profiles" if is_group else "user_profiles"
    col = "chat_id" if is_group else "user_id"
    
    async with await get_db() as db:
        async with db.execute(f"SELECT summary FROM {table} WHERE {col} = ?", (profile_id,)) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else ""

async def save_profile_summary(profile_id: int, summary: str, is_group: bool = False):
    """
    Saves or updates profile summary.
    """
    table = "group_profiles" if is_group else "user_profiles"
    col = "chat_id" if is_group else "user_id"
    now = int(time.time())
    
    async with await get_db() as db:
        await db.execute(
            f"INSERT OR REPLACE INTO {table} ({col}, summary, last_seen) VALUES (?, ?, ?)",
            (profile_id, summary, now)
        )
        await db.commit()

# Whitelist / Blacklist Dynamic Storage
async def add_chat_to_list(chat_id: int, list_type: str):
    async with await get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO whitelists (chat_id, list_type) VALUES (?, ?)",
            (chat_id, list_type)
        )
        await db.commit()

async def remove_chat_from_list(chat_id: int):
    async with await get_db() as db:
        await db.execute("DELETE FROM whitelists WHERE chat_id = ?", (chat_id,))
        await db.commit()

async def get_dynamic_list(list_type: str) -> set[int]:
    async with await get_db() as db:
        async with db.execute("SELECT chat_id FROM whitelists WHERE list_type = ?", (list_type,)) as cursor:
            rows = await cursor.fetchall()
    return {row[0] for row in rows}
