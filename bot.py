import aiohttp, asyncio, sqlite3, re, os
from telegram import *
from telegram.ext import *

BOT_TOKEN = os.getenv("BOT_TOKEN")

API = "https://tempmail-api-xi.vercel.app/api/mail"

db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY,email TEXT)")
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
def get_user(uid):
    cur.execute("SELECT email FROM users WHERE uid=?", (uid,))
    r = cur.fetchone()
    return None if not r else r[0]

def find_otp(text):
    x = re.findall(r"\b\d{4,8}\b", text)
    return x[0] if x else None

# ================= CREATE MAIL =================
async def create_mail():
    async with session.get(API) as r:
        data = await r.json()
    return data["email"]

# ================= PANEL =================
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

    email = await create_mail()

    cur.execute("REPLACE INTO users VALUES (?,?)",(uid,email))
    cur.execute("DELETE FROM seen WHERE uid=?", (uid,))
    db.commit()

    await update.message.reply_text(panel(email),
        parse_mode="Markdown",
        reply_markup=kb()
    )

# ================= GLOBAL =================
async def global_notify(context):
    cur.execute("SELECT uid,email FROM users")
    users = cur.fetchall()

    for uid, email in users:
        try:
            async with session.get(f"{API}?email={email}") as r:
                data = await r.json()
        except:
            continue

        for m in data.get("messages", []):
            mid = m["id"]

            cur.execute("SELECT 1 FROM seen WHERE uid=? AND mid=?", (uid,mid))
            if cur.fetchone():
                continue

            cur.execute("INSERT INTO seen VALUES (?,?)",(uid,mid))
            db.commit()

            body = m.get("body","")
            otp = find_otp(body)

            msg = f"📩 {m.get('subject','No subject')}"
            if otp:
                msg += f"\n🔐 OTP: `{otp}`"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Open Mail", callback_data=f"read_{mid}")]
            ])

            await context.bot.send_message(uid, msg,
                parse_mode="Markdown",
                reply_markup=keyboard
            )

        await asyncio.sleep(0.3)

# ================= INBOX =================
async def inbox(update, context):
    q = update.callback_query
    await q.answer()

    email = get_user(q.from_user.id)

    async with session.get(f"{API}?email={email}") as r:
        data = await r.json()

    buttons = []
    for m in data.get("messages", [])[:5]:
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

    email = get_user(q.from_user.id)
    mid = q.data.split("_")[1]

    async with session.get(f"{API}?email={email}") as r:
        data = await r.json()

    for m in data.get("messages", []):
        if m["id"] == mid:
            body = m.get("body","")
            otp = find_otp(body)

            msg = f"""
📂 {m.get('subject')}
👤 {m.get('from')}
"""

            if otp:
                msg += f"\n🔐 OTP: `{otp}`"

            msg += f"\n\n{body[:3000]}"

            break

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="inbox")]
    ])

    await q.message.edit_text(msg,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ================= REFRESH =================
async def refresh(update, context):
    q = update.callback_query
    await q.answer()

    email = get_user(q.from_user.id)

    await q.message.edit_text(panel(email),
        parse_mode="Markdown",
        reply_markup=kb()
    )

# ================= NEW =================
async def new(update, context):
    q = update.callback_query
    await q.answer()

    email = await create_mail()

    cur.execute("REPLACE INTO users VALUES (?,?)",(q.from_user.id,email))
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

    print("🔥 NEW API BOT RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
