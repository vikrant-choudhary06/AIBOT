import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType

import config
from utils.logger import logger
from utils.helpers import clean_text, is_hinglish, detect_tone, is_looping, is_duplicate_response
from memory.sqlite_memory import (
    save_message,
    get_chat_history,
    get_raw_history_texts,
    update_chat_style,
    get_style_summary,
    get_profile_summary,
    get_dynamic_list
)
from services.ollama import generate_response_stream
from services.humanizer import (
    TypingSimulator,
    check_and_update_cooldown,
    calculate_reading_delay,
    calculate_typing_delay,
    should_randomly_reply,
    should_react_instead_of_reply,
    send_reaction_safe
)

# Store self-info globally
self_user = None

async def init_self_user(client: Client):
    global self_user
    self_user = await client.get_me()
    logger.info(f"Userbot self-identity initialized: @{self_user.username} (ID: {self_user.id})")

async def is_chat_allowed(chat_id: int, chat_type: ChatType) -> bool:
    """
    Checks whitelist and blacklist tables + config file to decide if we can chat here.
    """
    # SQLite Dynamic Lists
    db_whitelist = await get_dynamic_list("whitelist")
    db_blacklist = await get_dynamic_list("blacklist")

    # Blacklist Check (Priority)
    if chat_id in config.BLACKLIST_CHATS or chat_id in db_blacklist:
        return False

    # Private Chats are allowed by default (unless blacklisted)
    if chat_type == ChatType.PRIVATE:
        return True

    # Group Chats Whitelist Check
    # Combine config file whitelist and SQLite whitelist
    combined_whitelist = config.WHITELIST_CHATS.union(db_whitelist)
    if combined_whitelist:
        return chat_id in combined_whitelist

    # If no whitelist is defined, allow all group chats by default
    return True

@Client.on_message(filters.all, group=1)
async def main_chat_handler(client: Client, message: Message):
    global self_user
    if not self_user:
        # Fallback if not initialized
        self_user = await client.get_me()

    # --- Safety & Loop Checks ---
    
    # 1. Ignore outgoing messages (self-sent) to prevent self-loop triggers
    if message.outgoing or (message.from_user and message.from_user.is_self):
        # We still save our own messages to database to maintain history/context
        text = message.text or message.caption
        if text:
            await save_message(
                chat_id=message.chat.id,
                message_id=message.id,
                sender_id=self_user.id,
                sender_name=self_user.first_name or "Me",
                text=text,
                is_ai=True
            )
        return

    # 2. Ignore messages without text/caption
    raw_text = message.text or message.caption
    if not raw_text:
        return

    # 3. Ignore bots
    if message.from_user and message.from_user.is_bot:
        return

    # 4. Ignore forwarded spam
    if message.forward_date or message.forward_from or message.forward_from_chat:
        return

    # 5. Check whitelist / blacklist
    if not await is_chat_allowed(message.chat.id, message.chat.type):
        return

    # Extract sender details
    sender_id = message.from_user.id if message.from_user else 0
    sender_name = message.from_user.first_name if message.from_user else "Stranger"
    chat_id = message.chat.id

    # Clean text of mentions/tags
    cleaned_input = clean_text(raw_text, self_user.username)

    # Save incoming message to database
    await save_message(
        chat_id=chat_id,
        message_id=message.id,
        sender_id=sender_id,
        sender_name=sender_name,
        text=cleaned_input,
        is_ai=False
    )

    # Asynchronously update speaking style database (learning behavior)
    asyncio.create_task(update_chat_style(chat_id, cleaned_input))

    # --- Trigger Evaluation ---
    is_private = message.chat.type == ChatType.PRIVATE
    is_mentioned = False
    is_reply_to_me = False

    # Check if mentioned (supports username mentions, text mentions, and replies automatically via Pyrogram)
    if message.mentioned:
        is_mentioned = True

    # Secondary check for username in text (just in case Pyrogram cache hasn't loaded entity details)
    if not is_mentioned and self_user.username:
        username_lower = f"@{self_user.username.lower()}"
        if username_lower in raw_text.lower():
            is_mentioned = True

    # Secondary check for replies to me
    if message.reply_to_message:
        replied_msg = message.reply_to_message
        if replied_msg.from_user and replied_msg.from_user.id == self_user.id:
            is_reply_to_me = True

    # Determine if we should respond
    should_reply = False
    if is_private:
        # In DMs, always reply
        should_reply = True
    elif is_mentioned or is_reply_to_me:
        # In groups, reply if tagged, text-mentioned, or directly replied to
        should_reply = True
    elif should_randomly_reply(chat_id):
        # Otherwise, check random group discussion participation
        should_reply = True

    if not should_reply:
        return

    # Check cooldown / rate limits
    if await check_and_update_cooldown(chat_id):
        logger.info(f"Cooldown active for chat {chat_id}. Ignored.")
        return

    # --- Reaction Check (Casual Human Interaction) ---
    # 10% chance to react with emoji instead of replying, if not a direct DM question
    if not is_private and not is_mentioned and "?" not in cleaned_input:
        react, emoji = should_react_instead_of_reply()
        if react and emoji:
            await send_reaction_safe(client, chat_id, message.id, emoji)
            return

    # --- Dynamic Context & Prompt Preparation ---
    
    # 1. Fetch recent conversation history
    history = await get_chat_history(chat_id, limit=12)
    
    # 2. Fetch custom style / slang memories
    style_summary = await get_style_summary(chat_id)
    
    # 3. Fetch user and group profiles
    is_group = message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    profile_id = chat_id if is_group else sender_id
    profile_summary = await get_profile_summary(profile_id, is_group=is_group)

    # 4. Tone and Language detection
    tone = detect_tone(cleaned_input)
    hinglish_detected = is_hinglish(cleaned_input)

    # 5. Build system prompt
    prompt_directives = [config.PERSONALITY_PROMPT]
    
    if hinglish_detected:
        prompt_directives.append(
            "CRITICAL: The user is speaking in Hinglish (Hindi written in English text). "
            "You MUST reply in casual, friendly Hinglish. Use common Hinglish words "
            "like 'kya', 'hai', 'bhai', 'yaar', 'toh', 'nhi', 'kar', 'kuch', 'chal', 'rha' naturally. "
            "Do NOT use pure Hindi devanagari script or formal Hindi/Urdu. Write Hindi words using English alphabet."
        )
    else:
        prompt_directives.append("The conversation is in English. Keep it natural, casual, and brief.")

    # Add custom style adaptations
    if style_summary:
        prompt_directives.append(f"Adapt to the chat's local style guidelines:{style_summary}")

    # Add historical summary/profile memory
    if profile_summary:
        profile_type = "Group context" if is_group else "User details"
        prompt_directives.append(f"Keep this context in mind about the {profile_type}: {profile_summary}")

    # Inject specific tone directives
    if tone == "playful_roast":
        prompt_directives.append("The user is teasing or joking. Roast them back playfully and casually.")
    elif tone == "inquisitive":
        prompt_directives.append("The user is asking a question. Reply informatively but briefly.")
    elif tone == "annoyed":
        prompt_directives.append("The user seems annoyed. Keep your reply brief, calm, and friendly.")

    system_prompt = "\n".join(prompt_directives)

    # --- Simulated Delays & Response Generation ---

    # 1. Reading time delay
    reading_delay = calculate_reading_delay(cleaned_input)
    await asyncio.sleep(reading_delay)

    placeholder = None
    accumulated_text = ""
    last_edit_time = 0.0
    edit_cooldown = 1.6  # Throttling to prevent Telegram rate limit errors

    try:
        # Start showing typing indicator
        async with TypingSimulator(client, chat_id):
            # Connect to Ollama and fetch response chunks
            async for chunk in generate_response_stream(history, system_prompt):
                accumulated_text += chunk
                
                # Check for internal loop/repetition on the fly
                if is_looping(accumulated_text):
                    logger.warning("Repetitive loop detected in Ollama response stream. Stopping.")
                    break

                now = time.time()
                # Edit placeholder progressively if length is sufficient
                if len(accumulated_text) > 10 and (now - last_edit_time >= edit_cooldown):
                    if not placeholder:
                        # Send initial message
                        placeholder = await client.send_message(
                            chat_id=chat_id,
                            text="✍️ ...",
                            reply_to_message_id=message.id
                        )
                    try:
                        await client.edit_message_text(
                            chat_id=chat_id,
                            message_id=placeholder.id,
                            text=f"{accumulated_text} ✍️"
                        )
                        last_edit_time = now
                    except Exception as edit_err:
                        logger.debug(f"Failed to edit progressive chunk: {edit_err}")
            
            # Streaming finished or broken. Check if we have an output
            final_reply = accumulated_text.strip()
            if not final_reply:
                # If generation was empty, do not send anything or remove placeholder
                if placeholder:
                    await client.delete_messages(chat_id, placeholder.id)
                return

            # Check if this completed reply is a duplicate of recent history to avoid repeating ourselves
            past_responses = await get_raw_history_texts(chat_id, limit=3)
            if is_duplicate_response(final_reply, past_responses):
                logger.warning(f"Discarding duplicate response in chat {chat_id}: '{final_reply}'")
                if placeholder:
                    try:
                        await client.delete_messages(chat_id, placeholder.id)
                    except Exception:
                        pass
                return

            # Simulate typing completion delay based on length
            typing_delay = calculate_typing_delay(final_reply)
            # Subtract time already spent in streaming edits
            await asyncio.sleep(max(0.1, typing_delay - 2.0))

            if placeholder:
                # Final edit to remove streaming icons
                await client.edit_message_text(
                    chat_id=chat_id,
                    message_id=placeholder.id,
                    text=final_reply
                )
                final_message_id = placeholder.id
            else:
                # If the reply is short or stream was too fast and no placeholder was created, send directly
                sent_msg = await client.send_message(
                    chat_id=chat_id,
                    text=final_reply,
                    reply_to_message_id=message.id
                )
                final_message_id = sent_msg.id

            # Save generated AI response to database
            await save_message(
                chat_id=chat_id,
                message_id=final_message_id,
                sender_id=self_user.id,
                sender_name=self_user.first_name or "Me",
                text=final_reply,
                is_ai=True
            )

    except Exception as e:
        logger.error(f"Error in chat handler: {e}")
        if placeholder:
            try:
                await client.delete_messages(chat_id, placeholder.id)
            except Exception:
                pass
