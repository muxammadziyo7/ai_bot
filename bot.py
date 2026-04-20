import os
import sqlite3
import requests
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MODEL = "llama-3.3-70b-versatile"
DB_NAME = "chats.db"


# ===================== DATABASE =====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            mode TEXT DEFAULT 'default'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT
        )
    """)

    conn.commit()
    conn.close()


def get_user_mode(user_id: int) -> str:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("SELECT mode FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    conn.close()

    if row:
        return row[0]
    return "default"


def set_user_mode(user_id: int, mode: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("INSERT OR IGNORE INTO users(user_id, mode) VALUES (?, ?)", (user_id, mode))
    cur.execute("UPDATE users SET mode=? WHERE user_id=?", (mode, user_id))

    conn.commit()
    conn.close()


def clear_chat(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("DELETE FROM messages WHERE user_id=?", (user_id,))

    conn.commit()
    conn.close()


def save_message(user_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO messages(user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content)
    )

    conn.commit()
    conn.close()


def get_history(user_id: int, limit: int = 15):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT role, content FROM messages
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT ?
    """, (user_id, limit))

    rows = cur.fetchall()
    conn.close()

    # reverse qilib qaytaramiz
    return list(reversed(rows))


# ===================== SYSTEM PROMPT =====================
def get_system_prompt(username: str, mode: str) -> str:
    if mode == "codex":
        return f"""
Sen AI Yordamchi - CODEX REJIMIDASAN.
Foydalanuvchi ismi: {username}

Qoidalar:
- Faqat dasturlash, kod yozish, debugging, framework, backend/frontend, API, algoritm bo'yicha yordam ber.
- Kodlarni to'liq yoz.
- Keraksiz gap yozma, professional bo'l.
- Javob o'zbek tilida, kod inglizcha bo'lsin.
"""
    else:
        return f"""
Sen AI Yordamchi.
Foydalanuvchi ismi: {username}

Qoidalar:
- O'zbek tilida tushunarli javob ber.
- Har qanday mavzuda yordam ber: dasturlash, o'yinlar, cybersecurity, kreativ, maslahat.
- Do'stona va aniq bo'l.
"""


# ===================== GROQ REQUEST =====================
def ask_groq(messages: list) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }

    data = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 1200
    }

    r = requests.post(url, headers=headers, json=data, timeout=60)

    if r.status_code != 200:
        try:
            err = r.json()
            return f"❌ API Error: {err}"
        except:
            return f"❌ API Error: {r.text}"

    response_json = r.json()
    return response_json["choices"][0]["message"]["content"]


# ===================== COMMANDS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.first_name if user else "Mehmon"

    set_user_mode(user.id, "default")

    await update.message.reply_text(
        f"👋 Assalomu alaykum, {username}!\n\n"
        "🤖 Men Groq AI botman.\n\n"
        "Buyruqlar:\n"
        "/new - yangi suhbat\n"
        "/codex - codex rejim\n"
        "/default - oddiy rejim\n"
        "/mode - hozirgi rejim\n\n"
        "✍️ Savolingizni yozing."
    )


async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clear_chat(user_id)
    await update.message.reply_text("✨ Yangi suhbat boshlandi! Chat tarix tozalandi.")


async def codex_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    set_user_mode(user_id, "codex")
    await update.message.reply_text("💻 Codex rejimi yoqildi! Endi faqat dasturlashga javob beraman.")


async def default_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    set_user_mode(user_id, "default")
    await update.message.reply_text("✅ Oddiy rejim yoqildi! Endi barcha mavzularda javob beraman.")


async def mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    m = get_user_mode(user_id)
    await update.message.reply_text(f"📌 Hozirgi rejim: {m}")


# ===================== MAIN CHAT HANDLER =====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.first_name if user else "Mehmon"

    user_text = update.message.text.strip()

    if not user_text:
        return

    mode = get_user_mode(user_id)

    # user message save
    save_message(user_id, "user", user_text)

    await update.message.chat.send_action("typing")

    history = get_history(user_id, limit=12)

    system_prompt = get_system_prompt(username, mode)

    messages = [{"role": "system", "content": system_prompt}]

    for role, content in history:
        messages.append({"role": role, "content": content})

    ai_reply = ask_groq(messages)

    # save assistant message
    save_message(user_id, "assistant", ai_reply)

    # Telegram limit: 4096
    if len(ai_reply) > 4000:
        for i in range(0, len(ai_reply), 4000):
            await update.message.reply_text(ai_reply[i:i+4000])
    else:
        await update.message.reply_text(ai_reply)


# ===================== RUN =====================
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN topilmadi (.env ni tekshir)")
        return

    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY topilmadi (.env ni tekshir)")
        return

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_chat))
    app.add_handler(CommandHandler("codex", codex_mode))
    app.add_handler(CommandHandler("default", default_mode))
    app.add_handler(CommandHandler("mode", mode))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot ishlayapti...")
    app.run_polling()


if __name__ == "__main__":
    main()