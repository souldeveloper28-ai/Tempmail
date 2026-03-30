import aiohttp, asyncio, random, string, sqlite3, re, os
from telegram import *
from telegram.ext import *

BOT_TOKEN = os.getenv("BOT_TOKEN")
API = "https://api.mail.tm"

# ================= DB =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY,email TEXT,token TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS seen(uid INTEGER,mid TEXT,PRIMARY KEY(uid, mid))")
db.commit()

# ================= UTILS =================
def rand(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def esc(t):
    return re.sub(r'([_*[\]()~`>#+-=|{}.!])', r'\\\1', t or "")

def get_user(uid):
    cur.execute("SELECT email,token FROM users WHERE uid=?", (uid,))
    r = cur.fetchone()
    return None if not r else {"email": r[0], "token": r[1]}

# ================= CREATE MAIL =================
async def create_mail():
    async with aiohttp.ClientSession() as s:
        d = await (await s.get(f"{API}/domains")).json()
        domain = random.choice(d["hydra:member"])["domain"]

        email = f"{rand()}@{domain}"
        password = rand(10)

        await s.post(f"{API}/accounts", json={"address": email, "password": password})
        t = await (await s.post(f"{API}/token", json={"address": email, "password": password})).json()

        return email, t["token"]

# ================= UI =================
def panel(email, count=0):
    return f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  ⚡ YASH OMEGA CYBER SYSTEM ⚡
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃
┃ 🟢 STATUS     : ONLINE
┃ 📡 CONNECTION : STABLE
┃ 🔐 SECURITY   : MAXIMUM
┃
┣━━ 📧 IDENTITY ━━━━━━━━━━━━━━━┫
┃ ⟿ `{email}`
┃
┣━━ 📊 LIVE DATA ━━━━━━━━━━━━━━┫
┃ ⟿ INBOX   : {count}
┃ ⟿ SPEED   : ULTRA FAST
┃ ⟿ MODE    : OMEGA CORE
┃
┣━━ 🧠 MODULES ━━━━━━━━━━━━━━━━┫
┃ ⟿ OTP SCANNER  : ACTIVE
┃ ⟿ AUTO TRACK   : ENABLED
┃ ⟿ SMART PARSER : ON
┃
┣━━ 🎛 CONTROL ━━━━━━━━━━━━━━━━┫
┃ ⟿ USE BUTTONS BELOW
┃
┣━━ 👑 CREDIT ━━━━━━━━━━━━━━━━┫
┃ ⟿ Build by Yash ⚡
┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
"""

def kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 INBOX", callback_data="refresh"),
         InlineKeyboardButton("⚡ NEW", callback_data="new")],
        [InlineKeyboardButton("🧠 SYSTEM", callback_data="system"),
         InlineKeyboardButton("⚙️ CONTROL", callback_data="menu")],
        [InlineKeyboardButton("🚀 BOOST", callback_data="boost")]
    ])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    email, token = await create_mail()

    cur.execute("REPLACE INTO users VALUES (?,?,?)", (uid, email, token))
    cur.execute("DELETE FROM seen WHERE uid=?", (uid,))
    db.commit()

    context.job_queue.run_repeating(notify, 2, chat_id=uid)

    await update.message.reply_text(panel(email), parse_mode="Markdown", reply_markup=kb())

# ================= NOTIFY =================
async def notify(context: ContextTypes.DEFAULT_TYPE):
    uid = context.job.chat_id
    u = get_user(uid)
    if not u:
        return

    async with aiohttp.ClientSession() as s:
        h = {"Authorization": f"Bearer {u['token']}"}
        data = await (await s.get(f"{API}/messages", headers=h)).json()

    for m in data.get("hydra:member", []):
        mid = m["id"]

        cur.execute("SELECT 1 FROM seen WHERE uid=? AND mid=?", (uid, mid))
        if cur.fetchone():
            continue

        cur.execute("INSERT INTO seen VALUES (?,?)", (uid, mid))
        db.commit()

        subject = m.get("subject", "")
        otp = re.findall(r"\b\d{4,8}\b", subject)

        msg = f"""
┏━━ 📩 NEW TRANSMISSION ━━┓
┃ 👤 `{m['from']['address']}`
┃ 📌 `{subject}`
"""

        if otp:
            msg += f"\n┃ ⚡ OTP: `{otp[0]}`"

        msg += "\n┗━━━━━━━━━━━━━━━━━━━━━━┛"

        await context.bot.send_message(
            uid,
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📂 OPEN", callback_data=f"read_{mid}")]
            ])
        )

# ================= READ =================
async def read_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    mid = q.data.split("_")[1]
    u = get_user(q.from_user.id)

    async with aiohttp.ClientSession() as s:
        h = {"Authorization": f"Bearer {u['token']}"}
        full = await (await s.get(f"{API}/messages/{mid}", headers=h)).json()

    body = full.get("text") or re.sub("<.*?>", "", full.get("html", ""))
    otp = re.findall(r"\b\d{4,8}\b", body)

    msg = f"""
┏━━ 📂 DATA PACKET ━━┓
┃ 👤 {esc(full['from']['address'])}
┃ 📌 {esc(full['subject'])}
┃
┃ 📜 {esc(body[:2000])}
"""

    if otp:
        msg += f"\n┃ ⚡ OTP: `{otp[0]}`"

    msg += "\n┗━━━━━━━━━━━━━━━━━━━━━━┛"

    await q.message.reply_text(msg, parse_mode="Markdown")

# ================= BUTTONS =================
async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    u = get_user(q.from_user.id)

    async with aiohttp.ClientSession() as s:
        h = {"Authorization": f"Bearer {u['token']}"}
        data = await (await s.get(f"{API}/messages", headers=h)).json()

    count = len(data.get("hydra:member", []))

    await q.message.edit_text(panel(u['email'], count), parse_mode="Markdown", reply_markup=kb())

async def new_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    email, token = await create_mail()

    cur.execute("REPLACE INTO users VALUES (?,?,?)", (q.from_user.id, email, token))
    cur.execute("DELETE FROM seen WHERE uid=?", (q.from_user.id,))
    db.commit()

    await q.message.edit_text(panel(email), parse_mode="Markdown", reply_markup=kb())

async def system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    await q.message.edit_text("""
┏━━━━━━━━━━━━━━━━━━━━━━┓
┃   🧠 SYSTEM MATRIX   ┃
┣━━━━━━━━━━━━━━━━━━━━━━┫
┃ 🤖 BOT      : ONLINE
┃ ⚡ SPEED    : OMEGA
┃ 📡 API      : STABLE
┃ 🔐 SECURITY : MAX
┃ 🧠 AI CORE  : ACTIVE
┃ 📊 TRACKING : LIVE
┃ 🚀 BOOST    : READY
┗━━━━━━━━━━━━━━━━━━━━━━┛
""", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 BACK", callback_data="refresh")]
    ]))

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    await q.message.edit_text("""
┏━━━━━━━━━━━━━━━━━━━━━━┓
┃   ⚙️ CONTROL HUB     ┃
┣━━━━━━━━━━━━━━━━━━━━━━┫
┃ 📡 FETCH INBOX
┃ ⚡ GENERATE MAIL
┃ 🧠 SCAN OTP
┃ 📊 SYSTEM STATUS
┃ 🚀 BOOST MODE
┗━━━━━━━━━━━━━━━━━━━━━━┛
""", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 Inbox", callback_data="refresh")],
        [InlineKeyboardButton("⚡ New Mail", callback_data="new")],
        [InlineKeyboardButton("🧠 System", callback_data="system")],
        [InlineKeyboardButton("🔙 Back", callback_data="refresh")]
    ]))

async def boost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    steps = [
        "⚡ Initializing...",
        "📡 Connecting...",
        "🧠 Loading AI...",
        "🚀 Boosting...",
        "✅ DONE"
    ]

    msg = await q.message.edit_text("⚡ Starting...")

    for s in steps:
        await asyncio.sleep(0.6)
        await msg.edit_text(f"```{s}```", parse_mode="Markdown")

    u = get_user(q.from_user.id)
    await msg.edit_text(panel(u['email']), parse_mode="Markdown", reply_markup=kb())

# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(refresh, pattern="refresh"))
    app.add_handler(CallbackQueryHandler(new_mail, pattern="new"))
    app.add_handler(CallbackQueryHandler(read_mail, pattern="^read_"))
    app.add_handler(CallbackQueryHandler(system, pattern="system"))
    app.add_handler(CallbackQueryHandler(menu, pattern="menu"))
    app.add_handler(CallbackQueryHandler(boost, pattern="boost"))

    print("🔥 YASH OMEGA BOT RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
