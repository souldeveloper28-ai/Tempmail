import aiohttp, asyncio, random, string, sqlite3, re, os, time
from telegram import *
from telegram.ext import *

BOT_TOKEN = os.getenv("BOT_TOKEN")
API = "https://api.mail.tm"

ADMIN_PASSWORD = "yashking"
ADMIN_TIMEOUT = 300

# ================= DB =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY,email TEXT,token TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS seen(uid INTEGER,mid TEXT,PRIMARY KEY(uid, mid))")
cur.execute("CREATE TABLE IF NOT EXISTS logs(uid INTEGER,action TEXT)")
db.commit()

session = None

# ================= SESSION =================
async def init_session(app):
    global session
    session = aiohttp.ClientSession()

async def close_session(app):
    if session:
        await session.close()

# ================= UTILS =================
def rand(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def get_user(uid):
    cur.execute("SELECT email,token FROM users WHERE uid=?", (uid,))
    r = cur.fetchone()
    return None if not r else {"email": r[0], "token": r[1]}

def log(uid, action):
    cur.execute("INSERT INTO logs VALUES (?,?)", (uid, action))
    db.commit()

# ================= AI =================
def ai(text):
    otp = re.findall(r"\b\d{4,8}\b", text)
    return otp[0] if otp else None

# ================= CREATE MAIL =================
async def create_mail():
    async with session.get(f"{API}/domains") as r:
        d = await r.json()

    domain = random.choice(d["hydra:member"])["domain"]
    email = f"{rand()}@{domain}"
    password = rand(10)

    await session.post(f"{API}/accounts", json={"address": email,"password": password})

    async with session.post(f"{API}/token", json={"address": email,"password": password}) as r:
        t = await r.json()

    return email, t["token"]

# ================= UI =================
def panel(email, count=0):
    return f"""
╔═══🌈 NEON CYBER CORE 🌈═══╗
║ 🟢 STATUS ➤ ONLINE
║ 📧 `{email}`
║ 📥 MAILS ➤ {count}
╠═══════════════════════════╣
║ 🧠 AI ➤ ACTIVE
║ 🚀 SPEED ➤ MAX
║ 🔐 SECURITY ➤ LOCKED
╠═══════════════════════════╣
║ 📩 MAIL TRACK ✔
║ 🔍 OTP SCAN ✔
║ ⚡ AUTO FETCH ✔
╠═══════════════════════════╣
║ 👑 YASH SYSTEM
╚═══════════════════════════╝
"""

def kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 INBOX", callback_data="inbox"),
         InlineKeyboardButton("⚡ NEW", callback_data="new")],
        [InlineKeyboardButton("🔄 REFRESH", callback_data="refresh"),
         InlineKeyboardButton("🚀 BOOST", callback_data="boost")],
        [InlineKeyboardButton("📊 LOGS", callback_data="logs"),
         InlineKeyboardButton("👑 ADMIN", callback_data="admin_login")]
    ])

# ================= START =================
async def start(update, context):
    uid = update.effective_user.id
    email, token = await create_mail()

    cur.execute("REPLACE INTO users VALUES (?,?,?)",(uid,email,token))
    cur.execute("DELETE FROM seen WHERE uid=?",(uid,))
    db.commit()

    log(uid,"start")

    await update.message.reply_text(panel(email), parse_mode="Markdown", reply_markup=kb())

# ================= GLOBAL LOOP =================
async def global_notify(context):
    cur.execute("SELECT uid,token FROM users")
    users = cur.fetchall()

    for uid, token in users:
        try:
            async with session.get(f"{API}/messages", headers={"Authorization": f"Bearer {token}"}) as r:
                data = await r.json()
        except:
            continue

        for m in data.get("hydra:member", []):
            mid = m["id"]

            cur.execute("SELECT 1 FROM seen WHERE uid=? AND mid=?", (uid,mid))
            if cur.fetchone(): continue

            cur.execute("INSERT INTO seen VALUES (?,?)",(uid,mid))
            db.commit()

            async with session.get(f"{API}/messages/{mid}",
                headers={"Authorization": f"Bearer {token}"}) as r:
                full = await r.json()

            body = full.get("text") or full.get("html","")
            otp = ai(body)

            msg = f"""
╔═══📡 NEON MAIL═══╗
║ 👤 {full['from']['address']}
║ 📌 {full['subject']}
"""

            if otp:
                msg += f"\n║ 🔐 OTP ➤ `⚡ {otp} ⚡`"

            msg += f"\n║ 📜 {body[:200]}\n╚══════════════════╝"

            await context.bot.send_message(uid, msg, parse_mode="Markdown")

        await asyncio.sleep(0.5)

# ================= INBOX =================
async def inbox(update, context):
    q = update.callback_query
    await q.answer()

    u = get_user(q.from_user.id)

    async with session.get(f"{API}/messages",
        headers={"Authorization": f"Bearer {u['token']}"}) as r:
        data = await r.json()

    msgs = data.get("hydra:member", [])[:5]

    buttons = []
    for m in msgs:
        buttons.append([InlineKeyboardButton(
            m['subject'][:30],
            callback_data=f"read_{m['id']}"
        )])

    await q.message.edit_text("📩 Select Mail:", reply_markup=InlineKeyboardMarkup(buttons))

# ================= READ MAIL =================
async def read_mail(update, context):
    q = update.callback_query
    await q.answer()

    mid = q.data.split("_")[1]
    u = get_user(q.from_user.id)

    async with session.get(f"{API}/messages/{mid}",
        headers={"Authorization": f"Bearer {u['token']}"}) as r:
        full = await r.json()

    body = full.get("text") or full.get("html","")
    otp = ai(body)

    msg = f"""
📂 FULL MAIL
👤 {full['from']['address']}
📌 {full['subject']}
"""

    if otp:
        msg += f"\n🔐 OTP: `⚡ {otp} ⚡`"

    msg += f"\n\n{body[:3000]}"

    await q.message.edit_text(msg, parse_mode="Markdown")

# ================= REFRESH =================
async def refresh(update, context):
    q = update.callback_query
    await q.answer()

    u = get_user(q.from_user.id)

    async with session.get(f"{API}/messages",
        headers={"Authorization": f"Bearer {u['token']}"}) as r:
        data = await r.json()

    count = len(data.get("hydra:member", []))

    await q.message.edit_text(panel(u['email'], count),
        parse_mode="Markdown", reply_markup=kb())

# ================= BOOST =================
async def boost(update, context):
    q = update.callback_query
    await q.answer()

    msg = await q.message.edit_text("⚡ BOOSTING...")
    for s in ["INIT","AI","SYNC","DONE"]:
        await asyncio.sleep(0.3)
        await msg.edit_text(s)

    await refresh(update, context)

# ================= ADMIN =================
async def admin_login(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("Enter password:")
    context.user_data["admin_login"] = True

async def handle_msg(update, context):
    uid = update.effective_user.id
    text = update.message.text

    log(uid,"msg")

    if context.user_data.get("admin_login"):
        if text == ADMIN_PASSWORD:
            context.user_data["is_admin"] = True
            context.user_data["admin_time"] = time.time()
            context.user_data["admin_login"] = False
            await update.message.reply_text("👑 ADMIN MODE")
        else:
            await update.message.reply_text("❌ Wrong")

# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.post_init = init_session
    app.post_shutdown = close_session

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(inbox, pattern="inbox"))
    app.add_handler(CallbackQueryHandler(read_mail, pattern="read_"))
    app.add_handler(CallbackQueryHandler(refresh, pattern="refresh"))
    app.add_handler(CallbackQueryHandler(boost, pattern="boost"))
    app.add_handler(CallbackQueryHandler(admin_login, pattern="admin_login"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    app.job_queue.run_repeating(global_notify, 5)

    print("🔥 FINAL SYSTEM RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
