import requests, random, string, os, sqlite3, asyncio
from datetime import datetime
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

def log_event(uid, text):
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{t}] UID:{uid} | {text}\n")

def create_mailbox():
    domain = requests.get(f"{API}/domains").json()["hydra:member"][0]["domain"]
    email = f"{rand_str()}@{domain}"
    password = rand_str(10)
    requests.post(f"{API}/accounts", json={"address": email, "password": password})
    token = requests.post(f"{API}/token", json={"address": email, "password": password}).json()["token"]
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

def delete_user(uid):
    cur.execute("DELETE FROM users WHERE uid=?", (uid,))
    conn.commit()

def keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
         InlineKeyboardButton("🔄 Refresh", callback_data="inbox")],
        [InlineKeyboardButton("🆕 New Mailbox", callback_data="newbox"),
         InlineKeyboardButton("🗑 Delete Mailbox", callback_data="clear")]
    ])

# ================= BOT HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)

    if not user:
        email, password, token = create_mailbox()
        save_user(uid, email, password, token)
        log_event(uid, f"MAILBOX CREATED | {email}")
    else:
        email = user[0]

    await update.message.reply_text(
        f"""📧 <b>Your Temp Mail</b>

<code>{escape(email)}</code>

{CREDIT}""",
        parse_mode="HTML",
        reply_markup=keyboard()
    )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await q.message.reply_text(f"📭 Inbox empty\n\n{CREDIT}", parse_mode="HTML", reply_markup=keyboard())
        return

    text = "📥 <b>Inbox</b>\n\n"
    kb = []

    for m in msgs[:7]:
        text += escape(m.get("subject") or "No Subject") + "\n"
        kb.append([
            InlineKeyboardButton("📖 Read", callback_data=f"read_{m['id']}"),
            InlineKeyboardButton("❌ Delete", callback_data=f"del_{m['id']}")
        ])

    await q.message.reply_text(text + "\n" + CREDIT, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

async def read(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    user = get_user(uid)
    token = user[2]
    mid = q.data.split("_", 1)[1]

    msg = requests.get(f"{API}/messages/{mid}", headers=headers(token)).json()

    await q.message.reply_text(
        f"""📨 <b>From:</b> {escape(msg['from']['address'])}
📌 <b>Subject:</b> {escape(msg.get('subject') or '')}

<pre>{escape(msg.get('text') or '')[:3500]}</pre>

{CREDIT}""",
        parse_mode="HTML",
        reply_markup=keyboard()
    )

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    user = get_user(uid)
    token = user[2]
    mid = q.data.split("_", 1)[1]

    requests.delete(f"{API}/messages/{mid}", headers=headers(token))
    await q.message.reply_text(f"🗑 Deleted\n\n{CREDIT}", parse_mode="HTML", reply_markup=keyboard())

async def newbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.callback_query.from_user.id
    delete_user(uid)
    await start(update, context)

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.callback_query.from_user.id
    delete_user(uid)
    await update.callback_query.message.reply_text("🗑 Mailbox deleted\n/start again")

# ================= AUTO NOTIFY LOOP =================

async def auto_notify_loop(app: Application):
    await asyncio.sleep(10)
    while True:
        cur.execute("SELECT uid, token, last_count FROM users")
        for uid, token, last in cur.fetchall():
            msgs = get_msgs(token)
            if len(msgs) > last:
                update_count(uid, len(msgs))
                try:
                    await app.bot.send_message(
                        uid,
                        f"📬 <b>New Mail Received!</b>\n\n{CREDIT}",
                        parse_mode="HTML",
                        reply_markup=keyboard()
                    )
                except:
                    pass
        await asyncio.sleep(30)

# ================= MAIN =================

async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(inbox, pattern="^inbox$"))
    app.add_handler(CallbackQueryHandler(read, pattern="^read_"))
    app.add_handler(CallbackQueryHandler(delete, pattern="^del_"))
    app.add_handler(CallbackQueryHandler(newbox, pattern="^newbox$"))
    app.add_handler(CallbackQueryHandler(clear, pattern="^clear$"))

    asyncio.create_task(auto_notify_loop(app))

    print("🤖 Bot running (NEVER STOP MODE)")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())