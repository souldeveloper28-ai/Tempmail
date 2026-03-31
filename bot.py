import aiohttp, asyncio, sqlite3, re, os
from telegram import *
from telegram.ext import *

BOT_TOKEN = os.getenv("BOT_TOKEN")
API = "https://tempmail-api-xi.vercel.app/api/mail"

db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER, email TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS active(uid INTEGER PRIMARY KEY, email TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS seen(uid INTEGER, mid TEXT, PRIMARY KEY(uid, mid))")
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
def parse_email(data):
    login, domain = data.split("|")
    return login, domain

def get_active(uid):
    cur.execute("SELECT email FROM active WHERE uid=?", (uid,))
    r = cur.fetchone()
    return None if not r else r[0]

def get_all(uid):
    cur.execute("SELECT email FROM users WHERE uid=?", (uid,))
    return [i[0] for i in cur.fetchall()]

def find_otp(text):
    x = re.findall(r"\b\d{4,8}\b", text)
    return x[0] if x else None

# ================= CREATE =================
async def create_mail():
    async with session.get(f"{API}?type=new") as r:
        d = await r.json()
    return d["email"], d["login"], d["domain"]

# ================= PANEL =================
def panel(email):
    return f"📧 `{email}`\n\n⚡ Multi TempMail Active\n🔐 Auto OTP ON"

def kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Inbox", callback_data="inbox"),
         InlineKeyboardButton("⚡ New", callback_data="new")],
        [InlineKeyboardButton("📂 My Emails", callback_data="list")],
        [InlineKeyboardButton("🗑 Delete", callback_data="delete")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]
    ])

# ================= START =================
async def start(update, context):
    uid = update.effective_user.id

    email, login, domain = await create_mail()
    data = f"{login}|{domain}"

    cur.execute("INSERT INTO users VALUES (?,?)",(uid,data))
    cur.execute("REPLACE INTO active VALUES (?,?)",(uid,data))
    db.commit()

    await update.message.reply_text(panel(email),
        parse_mode="Markdown",
        reply_markup=kb()
    )

# ================= GLOBAL OTP =================
async def global_notify(context):
    cur.execute("SELECT uid,email FROM active")
    users = cur.fetchall()

    for uid, data in users:
        login, domain = parse_email(data)

        try:
            async with session.get(f"{API}?type=inbox&login={login}&domain={domain}") as r:
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

            subject = m.get("subject","No subject")

            async with session.get(f"{API}?type=otp&login={login}&domain={domain}&id={mid}") as r:
                otp_data = await r.json()

            otp = otp_data.get("otp")

            msg = f"📩 {subject}"
            if otp:
                msg += f"\n🔐 OTP: `{otp}`"

            await context.bot.send_message(uid, msg, parse_mode="Markdown")

        await asyncio.sleep(0.3)

# ================= INBOX =================
async def inbox(update, context):
    q = update.callback_query
    await q.answer()

    data = get_active(q.from_user.id)
    login, domain = parse_email(data)

    async with session.get(f"{API}?type=inbox&login={login}&domain={domain}") as r:
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

    data = get_active(q.from_user.id)
    login, domain = parse_email(data)
    mid = q.data.split("_")[1]

    async with session.get(f"{API}?type=read&login={login}&domain={domain}&id={mid}") as r:
        d = await r.json()

    m = d["data"]
    body = m.get("body","")
    otp = find_otp(body)

    msg = f"📂 {m.get('subject')}\n👤 {m.get('from')}\n"
    if otp:
        msg += f"\n🔐 OTP: `{otp}`"

    msg += f"\n\n{body[:3000]}"

    await q.message.edit_text(msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="inbox")]])
    )

# ================= LIST =================
async def list_emails(update, context):
    q = update.callback_query
    await q.answer()

    emails = get_all(q.from_user.id)

    buttons = []
    for e in emails:
        login, domain = parse_email(e)
        buttons.append([
            InlineKeyboardButton(f"{login}@{domain}", callback_data=f"set_{e}")
        ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="refresh")])

    await q.message.edit_text("📂 Your Emails",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ================= SWITCH =================
async def set_email(update, context):
    q = update.callback_query
    await q.answer()

    data = q.data.replace("set_","")

    cur.execute("REPLACE INTO active VALUES (?,?)",(q.from_user.id,data))
    db.commit()

    login, domain = parse_email(data)
    email = f"{login}@{domain}"

    await q.message.edit_text(panel(email),
        parse_mode="Markdown",
        reply_markup=kb()
    )

# ================= DELETE =================
async def delete_email(update, context):
    q = update.callback_query
    await q.answer()

    data = get_active(q.from_user.id)

    cur.execute("DELETE FROM users WHERE uid=? AND email=?", (q.from_user.id,data))
    cur.execute("DELETE FROM active WHERE uid=?", (q.from_user.id,))
    db.commit()

    await q.message.edit_text("🗑 Email deleted. Create new one.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ New", callback_data="new")]
        ])
    )

# ================= NEW =================
async def new(update, context):
    q = update.callback_query
    await q.answer()

    email, login, domain = await create_mail()
    data = f"{login}|{domain}"

    cur.execute("INSERT INTO users VALUES (?,?)",(q.from_user.id,data))
    cur.execute("REPLACE INTO active VALUES (?,?)",(q.from_user.id,data))
    db.commit()

    await q.message.edit_text(panel(email),
        parse_mode="Markdown",
        reply_markup=kb()
    )

# ================= REFRESH =================
async def refresh(update, context):
    q = update.callback_query
    await q.answer()

    data = get_active(q.from_user.id)
    login, domain = parse_email(data)
    email = f"{login}@{domain}"

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
    app.add_handler(CallbackQueryHandler(list_emails, pattern="list"))
    app.add_handler(CallbackQueryHandler(set_email, pattern="set_"))
    app.add_handler(CallbackQueryHandler(delete_email, pattern="delete"))

    app.job_queue.run_repeating(global_notify, 3)

    print("🔥 FINAL GOD MULTI TEMPMAIL BOT RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
