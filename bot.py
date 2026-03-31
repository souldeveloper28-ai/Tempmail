import aiohttp, asyncio, sqlite3, re, os
from telegram import *
from telegram.ext import *

BOT_TOKEN = os.getenv("BOT_TOKEN")
API = "https://tempmail-api-xi.vercel.app/api/mail"

db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY,email TEXT,token TEXT,login TEXT,domain TEXT,provider TEXT)")
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
    cur.execute("SELECT * FROM users WHERE uid=?", (uid,))
    return cur.fetchone()

# ================= CREATE =================
async def create_mail():
    async with session.get(f"{API}?type=new") as r:
        d = await r.json()
    return d

# ================= UI =================
def panel(email, provider):
    return f"""
📧 `{email}`

⚡ Provider: {provider}
🔐 OTP Scanner: ON
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

    await update.message.reply_text("⚡ Creating email...")

    d = await create_mail()

    email = d["email"]
    provider = d.get("provider")

    token = d.get("token")
    login = d.get("login")
    domain = d.get("domain")

    cur.execute("REPLACE INTO users VALUES (?,?,?,?,?,?)",
                (uid,email,token,login,domain,provider))
    cur.execute("DELETE FROM seen WHERE uid=?", (uid,))
    db.commit()

    await update.message.reply_text(panel(email, provider),
        parse_mode="Markdown",
        reply_markup=kb()
    )

# ================= GLOBAL OTP =================
async def global_notify(context):
    cur.execute("SELECT uid,email,token,login,domain,provider FROM users")
    users = cur.fetchall()

    for uid,email,token,login,domain,provider in users:

        try:
            if provider == "mailtm":
                url = f"{API}?type=inbox&token={token}"
            else:
                url = f"{API}?type=inbox&login={login}&domain={domain}"

            async with session.get(url) as r:
                d = await r.json()
        except:
            continue

        for m in d.get("messages", []):
            mid = str(m["id"])

            cur.execute("SELECT 1 FROM seen WHERE uid=? AND mid=?", (uid,mid))
            if cur.fetchone():
                continue

            cur.execute("INSERT INTO seen VALUES (?,?)",(uid,mid))
            db.commit()

            # OTP fetch
            if provider == "mailtm":
                url = f"{API}?type=otp&token={token}&id={mid}"
            else:
                url = f"{API}?type=otp&login={login}&domain={domain}&id={mid}"

            async with session.get(url) as r:
                otp_data = await r.json()

            otp = otp_data.get("otp")

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
    user = get_user(uid)

    _,email,token,login,domain,provider = user

    if provider == "mailtm":
        url = f"{API}?type=inbox&token={token}"
    else:
        url = f"{API}?type=inbox&login={login}&domain={domain}"

    async with session.get(url) as r:
        d = await r.json()

    buttons = []
    for m in d.get("messages", [])[:5]:
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
    user = get_user(uid)

    _,email,token,login,domain,provider = user

    mid = q.data.split("_")[1]

    if provider == "mailtm":
        url = f"{API}?type=read&token={token}&id={mid}"
    else:
        url = f"{API}?type=read&login={login}&domain={domain}&id={mid}"

    async with session.get(url) as r:
        d = await r.json()

    m = d["data"]
    body = m.get("body","") + m.get("text","")

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

    user = get_user(q.from_user.id)
    _,email,_,_,_,provider = user

    await q.message.edit_text(panel(email, provider),
        parse_mode="Markdown",
        reply_markup=kb()
    )

# ================= NEW =================
async def new(update, context):
    q = update.callback_query
    await q.answer()

    d = await create_mail()

    cur.execute("REPLACE INTO users VALUES (?,?,?,?,?,?)",
                (q.from_user.id,d["email"],d.get("token"),d.get("login"),d.get("domain"),d.get("provider")))
    db.commit()

    await q.message.edit_text(panel(d["email"], d.get("provider")),
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

    print("🔥 FINAL PRO BOT RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
