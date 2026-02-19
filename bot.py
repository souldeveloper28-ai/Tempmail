import requests, random, string, sqlite3, re, os
from html import unescape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API = "https://api.mail.tm"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

# ================= DB =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users(
uid INTEGER PRIMARY KEY,
email TEXT,
password TEXT,
token TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS seen(
uid INTEGER,
mid TEXT,
PRIMARY KEY(uid, mid)
)""")
db.commit()

# ================= UTILS =================
def rand(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def clean_html(html):
    html = re.sub(r"<br\s*/?>", "\n", html)
    html = re.sub(r"</p>", "\n\n", html)
    html = re.sub(r"<.*?>", "", html)
    return unescape(html)

def otp(text):
    m = re.findall(r"\b\d{4,8}\b", text or "")
    return m[0] if m else None

def esc(t):
    return re.sub(r'([_*[\]()~`>#+-=|{}.!])', r'\\\1', t or "")

def get_user(uid):
    cur.execute("SELECT email,password,token FROM users WHERE uid=?", (uid,))
    r = cur.fetchone()
    return None if not r else {"email": r[0], "password": r[1], "token": r[2]}

# ================= CREATE MAIL =================
def create_mail():
    domain = random.choice(
        requests.get(f"{API}/domains", timeout=10).json()["hydra:member"]
    )["domain"]

    email = f"{rand()}@{domain}"
    password = rand(10)

    requests.post(f"{API}/accounts", json={
        "address": email,
        "password": password
    }, timeout=10)

    r = requests.post(f"{API}/token", json={
        "address": email,
        "password": password
    }, timeout=10).json()

    return email, password, r["token"]

# ================= KEYBOARD =================
def home_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ New / 🗑 Delete", callback_data="new")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]
    ])

def read_kb(mid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Read Mail", callback_data=f"read_{mid}")]
    ])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    email, password, token = create_mail()
    cur.execute("REPLACE INTO users VALUES (?,?,?,?)", (uid, email, password, token))
    cur.execute("DELETE FROM seen WHERE uid=?", (uid,))
    db.commit()

    for j in context.job_queue.jobs():
        if j.chat_id == uid:
            j.schedule_removal()

    context.job_queue.run_repeating(notify, 4, chat_id=uid)

    await update.message.reply_text(
        f"Your temporary email:\n\n`{email}`",
        parse_mode="Markdown",
        reply_markup=home_kb()
    )

# ================= AUTO NOTIFY =================
async def notify(context: ContextTypes.DEFAULT_TYPE):
    uid = context.job.chat_id
    u = get_user(uid)
    if not u:
        return

    h = {"Authorization": f"Bearer {u['token']}"}
    inbox = requests.get(f"{API}/messages", headers=h, timeout=10).json()["hydra:member"]

    for m in inbox:
        mid = m["id"]
        cur.execute("SELECT 1 FROM seen WHERE uid=? AND mid=?", (uid, mid))
        if cur.fetchone():
            continue

        cur.execute("INSERT INTO seen VALUES (?,?)", (uid, mid))
        db.commit()

        await context.bot.send_message(
            uid,
            f"📩 *New Mail*\n👤 {esc(m['from']['address'])}\n📌 {esc(m['subject'])}",
            parse_mode="Markdown",
            reply_markup=read_kb(mid)
        )

# ================= READ MAIL =================
async def read_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    mid = q.data.split("_", 1)[1]
    u = get_user(q.from_user.id)
    h = {"Authorization": f"Bearer {u['token']}"}

    full = requests.get(f"{API}/messages/{mid}", headers=h, timeout=10).json()
    body = full.get("text") or clean_html(full.get("html", ""))

    text = f"*From:* {esc(full['from']['address'])}\n*Subject:* {esc(full['subject'])}\n\n{esc(body)}"
    await q.message.reply_text(text[:4000], parse_mode="Markdown")

# ================= BUTTONS =================
async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)
    await q.message.edit_text(
        f"Your temporary email:\n\n`{u['email']}`",
        parse_mode="Markdown",
        reply_markup=home_kb()
    )

async def new_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    email, password, token = create_mail()
    cur.execute("REPLACE INTO users VALUES (?,?,?,?)",
                (q.from_user.id, email, password, token))
    cur.execute("DELETE FROM seen WHERE uid=?", (q.from_user.id,))
    db.commit()
    await q.message.edit_text(
        f"Your temporary email:\n\n`{email}`",
        parse_mode="Markdown",
        reply_markup=home_kb()
    )

# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(refresh, pattern="refresh"))
    app.add_handler(CallbackQueryHandler(new_mail, pattern="new"))
    app.add_handler(CallbackQueryHandler(read_mail, pattern="^read_"))

    print("🤖 BOT RUNNING STABLE")
    app.run_polling()

if __name__ == "__main__":
    main()
