import requests, random, string, os, sqlite3, asyncio
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN") or "PUT_YOUR_BOT_TOKEN"
API = "https://api.mail.tm"
DB_FILE = "users.db"

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
def rs(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def headers(token):
    return {"Authorization": f"Bearer {token}"}

def create_mailbox():
    domain = requests.get(f"{API}/domains").json()["hydra:member"][0]["domain"]
    email = f"{rs()}@{domain}"
    password = rs(10)
    requests.post(f"{API}/accounts", json={"address": email, "password": password})
    token = requests.post(
        f"{API}/token",
        json={"address": email, "password": password}
    ).json()["token"]
    return email, password, token

def get_msgs(token):
    return requests.get(
        f"{API}/messages",
        headers=headers(token)
    ).json().get("hydra:member", [])

def main_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
            InlineKeyboardButton("🔄 Refresh", callback_data="inbox")
        ],
        [
            InlineKeyboardButton("🆕 New Mail", callback_data="newbox"),
            InlineKeyboardButton("🗑 Delete", callback_data="clear")
        ]
    ])

# ================= BOT HANDLERS =================
async def start(update, context):
    uid = update.effective_user.id
    cur.execute("SELECT email FROM users WHERE uid=?", (uid,))
    row = cur.fetchone()

    if not row:
        email, pw, token = create_mailbox()
        cur.execute(
            "INSERT INTO users(uid,email,password,token,last_count) VALUES(?,?,?,?,0)",
            (uid, email, pw, token)
        )
        conn.commit()
    else:
        email = row[0]

    await update.message.reply_text(
        f"📧 <b>Your Temp Mail</b>\n\n<code>{escape(email)}</code>",
        parse_mode="HTML",
        reply_markup=main_kb()
    )

async def inbox(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    cur.execute("SELECT token FROM users WHERE uid=?", (uid,))
    row = cur.fetchone()
    if not row:
        await start(update, context)
        return

    msgs = get_msgs(row[0])
    cur.execute("UPDATE users SET last_count=? WHERE uid=?", (len(msgs), uid))
    conn.commit()

    if not msgs:
        await q.message.reply_text("📭 Inbox empty", reply_markup=main_kb())
        return

    text = "📥 <b>Inbox</b>\n\n"
    buttons = []
    for m in msgs[:7]:
        text += escape(m.get("subject") or "No Subject") + "\n"
        buttons.append([
            InlineKeyboardButton("📖 Read", callback_data=f"read_{m['id']}")
        ])

    await q.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def read(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    mid = q.data.split("_", 1)[1]

    cur.execute("SELECT token FROM users WHERE uid=?", (uid,))
    token = cur.fetchone()[0]

    msg = requests.get(
        f"{API}/messages/{mid}",
        headers=headers(token)
    ).json()

    await q.message.reply_text(
        f"<pre>{escape(msg.get('text') or '')[:3500]}</pre>",
        parse_mode="HTML",
        reply_markup=main_kb()
    )

async def newbox(update, context):
    uid = update.callback_query.from_user.id
    cur.execute("DELETE FROM users WHERE uid=?", (uid,))
    conn.commit()
    await start(update, context)

async def clear(update, context):
    uid = update.callback_query.from_user.id
    cur.execute("DELETE FROM users WHERE uid=?", (uid,))
    conn.commit()
    await update.callback_query.message.reply_text("🗑 Mailbox deleted")

# ================= AUTO NOTIFY =================
async def auto_notify(app):
    while True:
        cur.execute("SELECT uid, token, last_count FROM users")
        for uid, token, last in cur.fetchall():
            msgs = get_msgs(token)
            if len(msgs) > last:
                cur.execute(
                    "UPDATE users SET last_count=? WHERE uid=?",
                    (len(msgs), uid)
                )
                conn.commit()
                try:
                    await app.bot.send_message(uid, "📬 New mail received!")
                except:
                    pass
        await asyncio.sleep(30)

# ================= MAIN (EVENT LOOP SAFE) =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(inbox, pattern="^inbox$"))
    app.add_handler(CallbackQueryHandler(read, pattern="^read_"))
    app.add_handler(CallbackQueryHandler(newbox, pattern="^newbox$"))
    app.add_handler(CallbackQueryHandler(clear, pattern="^clear$"))

    # background task – SAFE (no asyncio.run, no await run_polling)
    app.post_init = lambda app: asyncio.create_task(auto_notify(app))

    print("🤖 BOT RUNNING STABLE")
    app.run_polling()

if __name__ == "__main__":
    main()
