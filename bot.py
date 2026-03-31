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

def find_otp(text):
    x = re.findall(r"\b\d{4,8}\b", text)
    return x[0] if x else None

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
📧 `{email}`

📥 Inbox: {count}
⚡ Temp Mail Active
🔐 OTP Scanner ON
"""

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Inbox", callback_data="inbox"),
         InlineKeyboardButton("⚡ New Mail", callback_data="new")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]
    ])

# ================= START =================
async def start(update, context):
    uid = update.effective_user.id

    email, token = await create_mail()
    cur.execute("REPLACE INTO users VALUES (?,?,?)",(uid,email,token))
    cur.execute("DELETE FROM seen WHERE uid=?",(uid,))
    db.commit()

    await update.message.reply_text(
        panel(email),
        parse_mode="Markdown",
        reply_markup=main_kb()
    )

# ================= GLOBAL MAIL =================
async def global_notify(context):
    cur.execute("SELECT uid,token FROM users")
    users = cur.fetchall()

    for uid, token in users:
        try:
            async with session.get(f"{API}/messages",
                headers={"Authorization": f"Bearer {token}"}) as r:
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
            otp = find_otp(body)

            msg = f"📩 {full['subject']}"
            if otp:
                msg += f"\n🔐 OTP: `{otp}`"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Open Mail", callback_data=f"read_{mid}")]
            ])

            await context.bot.send_message(uid, msg, parse_mode="Markdown", reply_markup=kb)

        await asyncio.sleep(0.5)

# ================= INBOX =================
async def inbox(update, context):
    q = update.callback_query
    await q.answer()

    u = get_user(q.from_user.id)

    async with session.get(f"{API}/messages",
        headers={"Authorization": f"Bearer {u['token']}"}) as r:
        data = await r.json()

    buttons = []
    for m in data.get("hydra:member", [])[:5]:
        buttons.append([
            InlineKeyboardButton(m['subject'][:30], callback_data=f"read_{m['id']}")
        ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="refresh")])

    await q.message.edit_text(
        "📩 Inbox",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

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
    otp = find_otp(body)

    msg = f"""
📂 {full['subject']}
👤 {full['from']['address']}
"""

    if otp:
        msg += f"\n🔐 OTP: `{otp}`"

    msg += f"\n\n{body[:3000]}"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Inbox", callback_data="inbox")]
    ])

    await q.message.edit_text(msg, parse_mode="Markdown", reply_markup=kb)

# ================= REFRESH =================
async def refresh(update, context):
    q = update.callback_query
    await q.answer()

    u = get_user(q.from_user.id)

    async with session.get(f"{API}/messages",
        headers={"Authorization": f"Bearer {u['token']}"}) as r:
        data = await r.json()

    await q.message.edit_text(
        panel(u['email'], len(data.get("hydra:member", []))),
        parse_mode="Markdown",
        reply_markup=main_kb()
    )

# ================= NEW MAIL =================
async def new(update, context):
    q = update.callback_query
    await q.answer()

    email, token = await create_mail()
    cur.execute("REPLACE INTO users VALUES (?,?,?)",(q.from_user.id,email,token))
    db.commit()

    await q.message.edit_text(panel(email), parse_mode="Markdown", reply_markup=main_kb())

# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.post_init = init_session
    app.post_shutdown = close_session

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(inbox, pattern="inbox"))
    app.add_handler(CallbackQueryHandler(read_mail, pattern="read_"))
    app.add_handler(CallbackQueryHandler(refresh, pattern="refresh"))
    app.add_handler(CallbackQueryHandler(new, pattern="new"))

    app.job_queue.run_repeating(global_notify, 5)

    print("🔥 REAL TEMP MAIL BOT RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
