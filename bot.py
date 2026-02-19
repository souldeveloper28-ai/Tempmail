import requests, random, string, os, sqlite3, asyncio
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
API = "https://api.mail.tm"
DB = "users.db"

# ===== DATABASE =====
conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users(
 uid INTEGER PRIMARY KEY,
 email TEXT,
 password TEXT,
 token TEXT,
 last_count INTEGER DEFAULT 0
)
""")
conn.commit()

# ===== HELPERS =====
def r(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def h(t):
    return {"Authorization": f"Bearer {t}"}

def create_mail():
    domain = requests.get(f"{API}/domains").json()["hydra:member"][0]["domain"]
    email = f"{r()}@{domain}"
    password = r(10)
    requests.post(f"{API}/accounts", json={"address": email, "password": password})
    token = requests.post(
        f"{API}/token",
        json={"address": email, "password": password}
    ).json()["token"]
    return email, password, token

def msgs(token):
    return requests.get(f"{API}/messages", headers=h(token)).json().get("hydra:member", [])

def kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Inbox", callback_data="inbox"),
         InlineKeyboardButton("🔄 Refresh", callback_data="inbox")]
    ])

# ===== BOT =====
async def start(update, ctx):
    uid = update.effective_user.id
    cur.execute("SELECT email FROM users WHERE uid=?", (uid,))
    row = cur.fetchone()

    if not row:
        e,p,t = create_mail()
        cur.execute(
            "INSERT INTO users(uid,email,password,token) VALUES(?,?,?,?)",
            (uid,e,p,t)
        )
        conn.commit()
    else:
        e = row[0]

    await update.message.reply_text(
        f"📧 Your Temp Mail\n\n{escape(e)}",
        reply_markup=kb()
    )

async def inbox(update, ctx):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    cur.execute("SELECT token FROM users WHERE uid=?", (uid,))
    row = cur.fetchone()
    if not row:
        await start(update, ctx)
        return

    m = msgs(row[0])
    if not m:
        await q.message.reply_text("📭 Inbox empty", reply_markup=kb())
        return

    text = "📥 Inbox\n\n"
    for x in m[:5]:
        text += (x.get("subject") or "No Subject") + "\n"

    await q.message.reply_text(text, reply_markup=kb())

# ===== AUTO NOTIFY =====
async def notify(app):
    while True:
        cur.execute("SELECT uid, token, last_count FROM users")
        for uid, token, last in cur.fetchall():
            m = msgs(token)
            if len(m) > last:
                cur.execute(
                    "UPDATE users SET last_count=? WHERE uid=?",
                    (len(m), uid)
                )
                conn.commit()
                try:
                    await app.bot.send_message(uid, "📬 New mail received!")
                except:
                    pass
        await asyncio.sleep(30)

# ===== MAIN (IMPORTANT) =====
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(inbox, pattern="^inbox$"))

    # background task – SAFE
    app.post_init = lambda app: asyncio.create_task(notify(app))

    print("BOT RUNNING SAFE")
    app.run_polling()

if __name__ == "__main__":
    main()
