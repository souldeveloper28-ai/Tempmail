import requests, random, string, os, sqlite3, asyncio
from datetime import datetime
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN") or "PUT_YOUR_BOT_TOKEN"
ADMIN_ID = int(os.getenv("ADMIN_ID") or 123456789)

API = "https://api.mail.tm"
DB_FILE = "users.db"
LOG_FILE = "admin_logs.txt"
CREDIT = "<i>— Credit: @YAsHSTARK_18</i>"

# ================= DATABASE =================

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    uid INTEGER PRIMARY KEY,
    email TEXT,
    password TEXT,
    token TEXT,
    last_count INTEGER DEFAULT 0
)
""")
conn.commit()

# ================= HELPERS =================

def rand_str(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def headers(token):
    return {"Authorization": f"Bearer {token}"}

def create_mailbox():
    domain = requests.get(f"{API}/domains").json()["hydra:member"][0]["domain"]
    email = f"{rand_str()}@{domain}"
    password = rand_str(10)
    requests.post(f"{API}/accounts", json={"address": email, "password": password})
    token = requests.post(
        f"{API}/token",
        json={"address": email, "password": password}
    ).json()["token"]
    return email, password, token

def get_msgs(token):
    return requests.get(f"{API}/messages", headers=headers(token)).json().get("hydra:member", [])

def get_user(uid):
    cur.execute("SELECT email, password, token, last_count FROM users WHERE uid=?", (uid,))
    return cur.fetchone()

def save_user(uid, email, password, token):
    cur.execute(
        "REPLACE INTO users (uid, email, password, token, last_count) VALUES (?, ?, ?, ?, 0)",
        (uid, email, password, token)
    )
    conn.commit()

def update_count(uid, count):
    cur.execute("UPDATE users SET last_count=? WHERE uid=?", (count, uid))
    conn.commit()

def keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
            InlineKeyboardButton("🔄 Refresh", callback_data="inbox")
        ],
        [
            InlineKeyboardButton("🆕 New Mailbox", callback_data="newbox"),
            InlineKeyboardButton("🗑 Delete Mailbox", callback_data="clear")
        ]
    ])

# ================= BOT HANDLERS =================

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)

    if not user:
        email, password, token = create_mailbox()
        save_user(uid, email, password, token)
    else:
        email = user[0]

    await update.message.reply_text(
        f"""📧 <b>Your Temp Mail</b>

<code>{escape(email)}</code>

{CREDIT}""",
        parse_mode="HTML",
        reply_markup=keyboard()
    )

async def inbox(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    user = get_user(uid)
    if not user:
        await start(update, context)
        return

    token = user[2]
    msgs = get_msgs(token)
    update_count(uid, len(msgs))

    if not msgs:
        await q.message.reply_text("📭 Inbox empty", reply_markup=keyboard())
        return

    text = "📥 <b>Inbox</b>\n\n"
    kb = []
    for m in msgs[:7]:
        text += escape(m.get("subject") or "No Subject") + "\n"
        kb.append([
            InlineKeyboardButton("📖 Read", callback_data=f"read_{m['id']}")
        ])

    await q.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

async def read(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    mid = q.data.split("_", 1)[1]

    token = get_user(uid)[2]
    msg = requests.get(f"{API}/messages/{mid}", headers=headers(token)).json()

    await q.message.reply_text(
        f"<pre>{escape(msg.get('text') or '')[:3500]}</pre>",
        parse_mode="HTML",
        reply_markup=keyboard()
    )

# ================= AUTO NOTIFY (SAFE WAY) =================

async def auto_notify(app):
    while True:
        cur.execute("SELECT uid, token, last_count FROM users")
        for uid, token, last in cur.fetchall():
            msgs = get_msgs(token)
            if len(msgs) > last:
                update_count(uid, len(msgs))
                try:
                    await app.bot.send_message(
                        uid,
                        "📬 <b>New Mail Received!</b>",
                        parse_mode="HTML",
                        reply_markup=keyboard()
                    )
                except:
                    pass
        await asyncio.sleep(30)

# ================= MAIN =================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(inbox, pattern="^inbox$"))
    app.add_handler(CallbackQueryHandler(read, pattern="^read_"))

    # ✅ SAFE background task
    app.post_init = lambda app: asyncio.create_task(auto_notify(app))

    print("🤖 Bot running (EVENT LOOP FIXED)")
    app.run_polling()

if __name__ == "__main__":
    main()
