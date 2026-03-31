import aiohttp, asyncio, sqlite3, re, os
from telegram import *
from telegram.ext import *

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ================= DB =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS user(uid INTEGER PRIMARY KEY,email TEXT,token TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS seen(mid TEXT PRIMARY KEY)")
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
    cur.execute("SELECT email,token FROM user WHERE uid=?", (uid,))
    return cur.fetchone()

# ================= CREATE MAIL =================
async def create_mail():
    async with session.get("https://api.mail.tm/domains") as r:
        d = await r.json()

    domain = d["hydra:member"][0]["domain"]
    login = "user" + str(asyncio.get_event_loop().time())[-6:]
    password = "pass123456"

    data = {"address": f"{login}@{domain}", "password": password}

    await session.post("https://api.mail.tm/accounts", json=data)

    async with session.post("https://api.mail.tm/token", json=data) as r:
        tok = await r.json()

    return data["address"], tok["token"]

# ================= UI =================
def panel(email):
    return f"""
╔══ 📧 TEMP MAIL ══╗

`{email}`

🟢 Active
🔐 OTP Detection ON

╚══════════════════╝
"""

def kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ New Email", callback_data="new")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]
    ])

# ================= START =================
async def start(update, context):
    uid = update.effective_user.id

    email, token = await create_mail()
    cur.execute("REPLACE INTO user VALUES (?,?,?)",(uid,email,token))
    cur.execute("DELETE FROM seen")
    db.commit()

    await update.message.reply_text(panel(email),
        parse_mode="Markdown",
        reply_markup=kb()
    )

# ================= AUTO MAIL =================
async def check_mail(context):
    cur.execute("SELECT uid,email,token FROM user")
    data = cur.fetchall()

    for uid,email,token in data:
        try:
            headers = {"Authorization": f"Bearer {token}"}

            async with session.get("https://api.mail.tm/messages", headers=headers) as r:
                d = await r.json()
        except:
            continue

        for m in d.get("hydra:member", []):
            mid = str(m["id"])

            cur.execute("SELECT 1 FROM seen WHERE mid=?", (mid,))
            if cur.fetchone():
                continue

            cur.execute("INSERT INTO seen VALUES (?)",(mid,))
            db.commit()

            async with session.get(f"https://api.mail.tm/messages/{mid}", headers=headers) as r:
                mail = await r.json()

            body = (mail.get("text","") + mail.get("html",""))
            otp = find_otp(body)

            msg = f"📩 *{m.get('subject','Mail')}*\n\n"

            if otp:
                msg += f"🔐 OTP: `{otp}`\n\n"

            msg += body[:300]

            await context.bot.send_message(uid, msg, parse_mode="Markdown")

# ================= NEW =================
async def new(update, context):
    q = update.callback_query
    await q.answer()

    email, token = await create_mail()
    cur.execute("REPLACE INTO user VALUES (?,?,?)",(q.from_user.id,email,token))
    cur.execute("DELETE FROM seen")
    db.commit()

    await q.message.edit_text(panel(email),
        parse_mode="Markdown",
        reply_markup=kb()
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

# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.post_init = init_session
    app.post_shutdown = close_session

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(new, pattern="new"))
    app.add_handler(CallbackQueryHandler(refresh, pattern="refresh"))

    app.job_queue.run_repeating(check_mail, 3)

    print("🔥 Temp Mail Bot Running")
    app.run_polling()

if __name__ == "__main__":
    main()
