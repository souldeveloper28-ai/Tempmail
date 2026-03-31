import aiohttp, asyncio, sqlite3, re, os, time, random
from telegram import *
from telegram.ext import *

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ================= DB =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS emails(uid INTEGER,email TEXT,token TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS seen(uid INTEGER,mid TEXT,PRIMARY KEY(uid, mid))")
db.commit()

# ================= GLOBAL =================
session = None
CACHE = set()
RETRY = []
STATS = {"mails":0,"otp":0,"fail":0}
MODE = {"burst":True,"silent":False}
LAST = time.time()

# ================= SESSION =================
async def init_session(app):
    global session
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=120))

async def close_session(app):
    if session:
        await session.close()

# ================= UTILS =================
def otp(text):
    m = re.findall(r"\b\d{4,8}\b", text)
    return m[0] if m else None

def get_all(uid):
    cur.execute("SELECT email,token FROM emails WHERE uid=?", (uid,))
    return cur.fetchall()

# ================= CREATE =================
async def create():
    async with session.get("https://api.mail.tm/domains") as r:
        d = await r.json()

    domain = d["hydra:member"][0]["domain"]
    login = "x" + str(random.randint(100000,999999))
    password = "pass123456"

    data = {"address": f"{login}@{domain}", "password": password}

    await session.post("https://api.mail.tm/accounts", json=data)

    async with session.post("https://api.mail.tm/token", json=data) as r:
        tok = await r.json()

    return data["address"], tok["token"]

# ================= UI =================
def panel(emails):
    return f"""
╔══ ⚡ 500 SYSTEM ══╗

📊 Emails: {len(emails)}
📩 {STATS['mails']} | 🔐 {STATS['otp']} | ❌ {STATS['fail']}

⚡ Mode: {'BURST' if MODE['burst'] else 'SAFE'}
🔇 Silent: {MODE['silent']}

╚═══════════════════╝
"""

def kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Add", callback_data="new")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")],
        [InlineKeyboardButton("🧠 Mode", callback_data="mode")],
        [InlineKeyboardButton("🔇 Silent", callback_data="silent")]
    ])

# ================= FETCH =================
async def fetch(u,e,t,ctx):
    global LAST

    try:
        h = {"Authorization": f"Bearer {t}"}
        async with session.get("https://api.mail.tm/messages", headers=h) as r:
            d = await r.json()
    except:
        STATS["fail"]+=1
        RETRY.append((u,e,t))
        return

    msgs = d.get("hydra:member", [])

    # OTP priority
    msgs.sort(key=lambda x:"otp" in x.get("subject","").lower(),reverse=True)

    for m in msgs:
        mid = str(m["id"])

        if mid in CACHE:
            continue

        cur.execute("SELECT 1 FROM seen WHERE uid=? AND mid=?", (u,mid))
        if cur.fetchone():
            continue

        CACHE.add(mid)
        cur.execute("INSERT INTO seen VALUES (?,?)",(u,mid))
        db.commit()

        async with session.get(f"https://api.mail.tm/messages/{mid}", headers=h) as r:
            mail = await r.json()

        body = (mail.get("text","")+mail.get("html",""))
        code = otp(body)

        STATS["mails"]+=1
        if code:
            STATS["otp"]+=1

        if not MODE["silent"]:
            msg = f"📩 {m.get('subject','Mail')}\n\n"
            if code:
                msg += f"🔐 `{code}`\n\n"
            msg += body[:150]

            await ctx.bot.send_message(u,msg,parse_mode="Markdown")

        LAST = time.time()

# ================= ENGINE =================
async def engine(ctx):
    cur.execute("SELECT uid,email,token FROM emails")
    data = cur.fetchall()

    await asyncio.gather(*[fetch(u,e,t,ctx) for u,e,t in data])

    # retry
    while RETRY:
        u,e,t = RETRY.pop()
        await fetch(u,e,t,ctx)

    idle = time.time()-LAST
    delay = 0.1 if MODE["burst"] else 0.5
    if idle>30: delay=1

    await asyncio.sleep(delay)

# ================= LOOP =================
async def loop(ctx):
    while True:
        try:
            await engine(ctx)
        except:
            await asyncio.sleep(1)

# ================= CONTROLS =================
async def mode(update,ctx):
    MODE["burst"]=not MODE["burst"]
    await update.callback_query.answer("Mode toggled")

async def silent(update,ctx):
    MODE["silent"]=not MODE["silent"]
    await update.callback_query.answer("Silent toggled")

# ================= COMMANDS =================
async def start(update,ctx):
    u = update.effective_user.id
    e,t = await create()
    cur.execute("INSERT INTO emails VALUES (?,?,?)",(u,e,t))
    db.commit()

    await update.message.reply_text(panel(get_all(u)),
        parse_mode="Markdown",reply_markup=kb())

async def new(update,ctx):
    q=update.callback_query; await q.answer()
    e,t=await create()
    cur.execute("INSERT INTO emails VALUES (?,?,?)",(q.from_user.id,e,t))
    db.commit()
    await q.message.edit_text(panel(get_all(q.from_user.id)),
        parse_mode="Markdown",reply_markup=kb())

async def refresh(update,ctx):
    q=update.callback_query; await q.answer()
    await q.message.edit_text(panel(get_all(q.from_user.id)),
        parse_mode="Markdown",reply_markup=kb())

# ================= MAIN =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.post_init = init_session
    app.post_shutdown = close_session

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(new, pattern="new"))
    app.add_handler(CallbackQueryHandler(refresh, pattern="refresh"))
    app.add_handler(CallbackQueryHandler(mode, pattern="mode"))
    app.add_handler(CallbackQueryHandler(silent, pattern="silent"))

    app.job_queue.run_once(loop, 1)

    print("🔥 500 FEATURE SYSTEM RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
