# 🤖 AI Telegram Userbot (Ollama + Pyrogram)

A fully asynchronous, production-ready Telegram userbot written in Python 3.11+. It transforms your personal Telegram account into an AI-powered conversational partner using a local **Ollama** server running the **Gemma (2B)** model. 

The bot is designed to act naturally, simulate human-like typing flows, learn chat styles from groups, respond in Hinglish contextually, and manage safety logic to prevent spam or loops.

---

## ✨ Features

- **Local AI Inference**: Powered completely by your local Ollama server running `gemma:2b` (configurable). No API keys or cloud services required.
- **Human-like Chatting Flow**:
  - **Dynamic Hinglish Detection**: Automatically responds in Hinglish if the user speaks in Hinglish.
  - **Simulated Reading & Typing Delays**: Calculates typing speeds and reading delays based on message length.
  - **Typing Indicator**: Simulates the Telegram typing action continuously while Ollama generates responses.
  - **Incremental Streaming Updates**: Edit messages progressively as the stream returns from Ollama.
  - **Randomized Emoji Reactions**: Occasionally reacts with emojis (10% chance) instead of responding, imitating real chat dynamics.
- **Context & Memory Intelligence**:
  - **Conversation Logs**: Uses `aiosqlite` to store recent chat contexts, maintaining group/private conversation threads.
  - **Speaking Style Learning**: Learns slang, common emojis, and average reply length per chat to blend into groups.
  - **Per-User/Group Contexts**: Persists custom personality prompts and lightweight context summaries.
- **Robust Safety Guardrails**:
  - **Self-Loop Protection**: Ignores its own triggers and output repetitions.
  - **Bot Filtering**: Ignores other automated Telegram bots.
  - **Anti-Spam Cooldowns**: Enforces a configurable per-chat cooldown.
  - **Spam Filtering**: Ignores forwarded spam, media-only messages, and blocked users.
- **Dynamic Commands**: Manage whitelists, blacklists, and personality prompts directly from Telegram using commands.

---

## 📂 Project Structure

```
e:/AIBOT/
├── .env.example            # Environment variables template
├── requirements.txt        # Project dependencies
├── main.py                 # Application entrypoint & initializer
├── config.py               # Env loader & configuration validator
├── generate_session.py     # Interactive script to generate Telegram session strings
├── database/
│   └── db.py               # SQLite asynchronous database schema & initialization
├── memory/
│   └── sqlite_memory.py    # Memory logic (context extraction, style learning, profiles)
├── services/
│   ├── ollama.py           # Ollama async API Client (tags & chat endpoint)
│   └── humanizer.py        # Cooldowns, typing simulation, and delay calculations
├── plugins/
│   ├── chat.py             # Event handler for conversations & AI generation
│   └── commands.py         # Self-commands (.whitelist, .blacklist, .personality)
└── utils/
    ├── logger.py           # Standard logging setup (Console + File)
    └── helpers.py          # Helper utilities (Hinglish/tone checkers, text cleaners)
```

---

## 🚀 Setup Instructions

### Prerequisite 1: Local Ollama Setup
1. Download and install [Ollama](https://ollama.com).
2. Start the Ollama server on your machine.
3. Download the default Gemma model:
   ```bash
   ollama pull gemma:2b
   ```
4. Verify it's running by visiting `http://127.0.0.1:11434` in your browser.

### Prerequisite 2: Telegram API Credentials
1. Go to [my.telegram.org](https://my.telegram.org) and log in.
2. Navigate to **API development tools**.
3. Create a new application. You will get an `api_id` (integer) and `api_hash` (string).

---

### Installation & Run

#### Step 1: Clone or Open Workspace
Ensure your directory is set to `e:/AIBOT/`.

#### Step 2: Install Python Dependencies
Install the required packages using your Python environment (Python 3.11+ recommended):
```bash
pip install -r requirements.txt
```

#### Step 3: Generate Telegram Session String
Run the interactive helper script to log in and export your Pyrogram session string:
```bash
python generate_session.py
```
1. Enter your `API ID` and `API HASH`.
2. Enter your Telegram phone number (with country code, e.g., `+91XXXXXXXXXX`).
3. Enter the login code sent to your Telegram app.
4. If prompted, enter your 2-Step Verification password.
5. Copy the generated `SESSION_STRING` printed on your terminal.

#### Step 4: Configure Environment Variables
Copy `.env.example` to a new file named `.env`:
```bash
cp .env.example .env
```
Fill in the values in your `.env`:
```env
API_ID=your_api_id
API_HASH=your_api_hash
SESSION_STRING=your_session_string_from_step_3
OLLAMA_URL=http://127.0.0.1:11434
PRIMARY_MODEL=qwen2.5:7b
FALLBACK_MODEL=mistral
```

---

## 🏃 Running the Userbot

Start the userbot by executing:
```bash
python main.py
```

The system will automatically:
1. Verify the `.env` values.
2. Initialize or connect to the local SQLite database (`database/userbot.db`).
3. Verify that your local Ollama is active and has the `gemma:2b` model loaded.
4. Establish the Pyrogram client connection and go online.

---

## 🛠️ Dynamic Telegram Commands

You can control the bot directly from any chat using the following command prefixes (only outgoing messages from your account will trigger them):

| Command | Usage | Description |
|---|---|---|
| `.whitelist` | `.whitelist` or `.whitelist <chat_id>` | Add the current chat (or specified ID) to the AI whitelist. |
| `.blacklist` | `.blacklist` or `.blacklist <chat_id>` | Add the current chat (or specified ID) to the blacklist. |
| `.personality` | `.personality <new prompt>` | Dynamically update the AI's base system prompt. |
| `.personality` | `.personality` | View the current active personality prompt. |
| `.clear_memory` | `.clear_memory` | Wipe conversation history and learned styles for the current chat. |

---

## ⚙️ How it Works under the Hood

1. **Context Memory**: Every incoming and outgoing message is saved to SQLite. When a new message triggers the bot, it retrieves the last 12 messages from that chat, formatting user messages with their names to help the AI understand who is speaking.
2. **Style Extraction**: The bot tracks vocabulary frequencies and emoji frequencies from group messages, dynamically injecting these patterns into the system instructions.
3. **Response Streaming**: The bot creates a typing placeholder (`✍️ ...`) and starts a background loop simulating the typing indicator. As Ollama yields response chunks, the userbot edits the message on Telegram, throttled at `1.6s` to comply with Telegram rate limits.
