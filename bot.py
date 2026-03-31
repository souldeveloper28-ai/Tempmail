import aiohttp, asyncio, sqlite3, re, os
from telegram import *
from telegram.ext import *

BOT_TOKEN = os.getenv("BOT_TOKEN")

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
def find_otp(text):
    x = re.findall(r"\b\d{4,8}\b", text)
    return x[0] if x else None

def get_user(uid):
    cur.execute("SELECT email,token FROM users WHERE uid=?", (uid,))
    return cur.fetchone()

# ================= CREATE =================
async def create_mail():
    async with session.get("https://api.mail.tm/domains") as r:
        d = await r.json()

    domain = d["hydra:member"][0]["domain"]
    login = "user" + str(int(asyncio.get_event_loop().time()*1000))[-6:]
    password = "pass123456"

    data = {"address": f"{login}@{domain}", "password": password}

    await session.post("https://api.mail.tm/accounts", json=data)

    async with session.post("https://api.mail.tm/token", json=data) as r:
        tok = await r.json()

    return data["address"], tok["token"]

# ================= UI =================
def panel(email):
    return f"""
📧 `{email}`

⚡ Temp Mail Active
🔐 OTP Scanner ON
"""

def kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Inbox", callback_data="inbox"),
         InlineKeyboardButton("⚡ New", callback_data="new")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]
    ])

# ================= START =================
async def start(update, context):
    uid = update.effective_user.id

    email, token = await create_mail()

    cur.execute("REPLACE INTO users VALUES (?,?,?)",(uid,email,token))
    cur.execute("DELETE FROM seen WHERE uid=?", (uid,))
    db.commit()

    await update.message.reply_text(panel(email),
        parse_mode="Markdown",
        reply_markup=kb()
    )

# ================= GLOBAL AUTO OTP =================
async def global_notify(context):
    cur.execute("SELECT uid,email,token FROM users")
    users = cur.fetchall()

    for uid,email,token in users:
        try:
            headers = {"Authorization": f"Bearer {token}"}

            async with session.get("https://api.mail.tm/messages", headers=headers) as r:
                d = await r.json()
        except:
            continue

        for m in d.get("hydra:member", []):
            mid = str(m["id"])

            cur.execute("SELECT 1 FROM seen WHERE uid=? AND mid=?", (uid,mid))
            if cur.fetchone():
                continue

            cur.execute("INSERT INTO seen VALUES (?,?)",(uid,mid))
            db.commit()

            async with session.get(f"https://api.mail.tm/messages/{mid}", headers=headers) as r:
                mail = await r.json()

            body = (mail.get("text","") + mail.get("html",""))
            otp = find_otp(body)

            msg = f"📩 {m.get('subject','Mail')}"
            if otp:
                msg += f"\n🔐 OTP: `{otp}`"

            await context.bot.send_message(uid, msg, parse_mode="Markdown")

        await asyncio.sleep(0.5)

# ================= INBOX =================
async def inbox(update, context):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    email, token = get_user(uid)

    headers = {"Authorization": f"Bearer {token}"}

    async with session.get("https://api.mail.tm/messages", headers=headers) as r:
        d = await r.json()

    buttons = []
    for m in d.get("hydra:member", [])[:5]:
        buttons.append([
            InlineKeyboardButton(m.get("subject","No subject")[:30],
                                 callback_data=f"read_{m['id']}")
        ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="refresh")])

    await q.message.edit_text("📩 Inbox",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ================= READ =================
async def read_mail(update, context):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    email, token = get_user(uid)

    mid = q.data.split("_")[1]

    headers = {"Authorization": f"Bearer {token}"}

    async with session.get(f"https://api.mail.tm/messages/{mid}", headers=headers) as r:
        m = await r.json()

    body = (m.get("text","") + m.get("html",""))
    otp = find_otp(body)

    msg = f"📂 {m.get('subject')}\n👤 {m.get('from')}\n"
    if otp:
        msg += f"\n🔐 OTP: `{otp}`"

    msg += f"\n\n{body[:3000]}"

    await q.message.edit_text(msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="inbox")]])
    )

# ================= REFRESH =================
async def refresh(update, context):
    q = update.callback_query
    await q.answer()

    email, _ = get_user(q.from_user.id)

    await q.message.edit_text(panel(email),
        parse_mode="Markdown",
        reply_markup=kb()
    )

# ================= NEW =================
async def new(update, context):
    q = update.callback_query
    await q.answer()

    email, token = await create_mail()

    cur.execute("REPLACE INTO users VALUES (?,?,?)",(q.from_user.id,email,token))
    db.commit()

    await q.message.edit_text(panel(email),
        parse_mode="Markdown",
        reply_markup=kb()
    )

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

    app.job_queue.run_repeating(global_notify, 3)

    print("🔥 MAIL.TM UI BOT RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
