import aiohttp, asyncio, random, string, sqlite3, re, os, time, atexit
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

# ================= SAFE CLOSE =================
@atexit.register
def close_session():
    global session
    if session:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(session.close())
            else:
                loop.run_until_complete(session.close())
        except:
            pass

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
    category = "OTP" if otp else "GENERAL"
    summary = text[:80]
    return otp[0] if otp else None, category, summary

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
╔══════════════════════════════════════╗
║ ⚡ YASH GOD CORE SYSTEM ⚡           ║
╠══════════════════════════════════════╣
║ 📧 `{email}`
║ 📥 Inbox : {count}
║ ⚡ Mode   : FULL POWER
╠══════════════════════════════════════╣
║ 🧠 AI SYSTEM : ACTIVE
║ 🚀 SPEED     : EXTREME
║ 🔐 SECURITY  : MAX
╠══════════════════════════════════════╣
║ 👑 KING CONTROL ENABLED
╚══════════════════════════════════════╝
"""

def kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Inbox", callback_data="inbox"),
         InlineKeyboardButton("⚡ New", callback_data="new")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
         InlineKeyboardButton("🚀 Boost", callback_data="boost")],
        [InlineKeyboardButton("📊 Logs", callback_data="logs"),
         InlineKeyboardButton("⚙️ Admin", callback_data="admin_login")]
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
                if r.status != 200: continue
                data = await r.json()
        except:
            continue

        for m in data.get("hydra:member", []):
            mid = m["id"]

            cur.execute("SELECT 1 FROM seen WHERE uid=? AND mid=?", (uid,mid))
            if cur.fetchone(): continue

            cur.execute("INSERT INTO seen VALUES (?,?)",(uid,mid))
            db.commit()

            otp, cat, summary = ai(m.get("subject",""))

            msg = f"""
📩 NEW MAIL
📌 {m['subject']}
🧠 Type: {cat}
"""
            if otp:
                msg += f"\n🔐 OTP: {otp}"

            await context.bot.send_message(uid, msg)

        await asyncio.sleep(0.3)

# ================= BUTTONS =================
async def inbox(update, context):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)

    async with session.get(f"{API}/messages", headers={"Authorization": f"Bearer {u['token']}"}) as r:
        data = await r.json()

    text = "📩 Inbox:\n"
    for m in data.get("hydra:member", [])[:10]:
        text += f"• {m['subject'][:30]}\n"

    await q.message.edit_text(text)

async def refresh(update, context):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)

    async with session.get(f"{API}/messages", headers={"Authorization": f"Bearer {u['token']}"}) as r:
        data = await r.json()

    await q.message.edit_text(panel(u['email'], len(data.get("hydra:member", []))),
                              parse_mode="Markdown", reply_markup=kb())

async def new(update, context):
    q = update.callback_query
    await q.answer()

    email, token = await create_mail()
    cur.execute("REPLACE INTO users VALUES (?,?,?)",(q.from_user.id,email,token))
    db.commit()

    await q.message.edit_text(panel(email), parse_mode="Markdown", reply_markup=kb())

async def boost(update, context):
    q = update.callback_query
    await q.answer()

    msg = await q.message.edit_text("⚡ BOOSTING...")
    for s in ["INIT","AI","SYNC","MAX","DONE"]:
        await asyncio.sleep(0.3)
        await msg.edit_text(s)

    await refresh(update, context)

# ================= ADMIN =================
def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="stats"),
         InlineKeyboardButton("👥 Users", callback_data="users")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast"),
         InlineKeyboardButton("🚫 Ban", callback_data="ban")],
        [InlineKeyboardButton("⚡ Force", callback_data="force"),
         InlineKeyboardButton("🗑 Reset", callback_data="reset")],
        [InlineKeyboardButton("🚪 Logout", callback_data="logout")]
    ])

def is_admin(context):
    if not context.user_data.get("is_admin"):
        return False
    if time.time() - context.user_data.get("admin_time",0) > ADMIN_TIMEOUT:
        context.user_data["is_admin"] = False
        return False
    return True

async def admin_login(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🔐 Enter Password:")
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
            await update.message.reply_text("👑 ADMIN MODE", reply_markup=admin_kb())
        else:
            await update.message.reply_text("❌ Wrong")
        return

    if context.user_data.get("broadcast") and is_admin(context):
        cur.execute("SELECT uid FROM users")
        for u in cur.fetchall():
            try:
                await context.bot.send_message(u[0], text)
            except: pass
        context.user_data["broadcast"] = False
        await update.message.reply_text("✅ Done")

    if context.user_data.get("force") and is_admin(context):
        cur.execute("SELECT uid FROM users")
        for u in cur.fetchall():
            try:
                await context.bot.send_message(u[0], f"⚠️ {text}")
            except: pass
        context.user_data["force"] = False

    if context.user_data.get("ban") and is_admin(context):
        cur.execute("DELETE FROM users WHERE uid=?", (int(text),))
        db.commit()
        context.user_data["ban"] = False
        await update.message.reply_text("🚫 Banned")

async def stats(update, context):
    if not is_admin(context): return
    q = update.callback_query
    await q.answer()

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM logs")
    logs = cur.fetchone()[0]

    await q.message.edit_text(f"👥 Users: {users}\n📊 Logs: {logs}", reply_markup=admin_kb())

async def users(update, context):
    if not is_admin(context): return
    q = update.callback_query
    await q.answer()

    cur.execute("SELECT uid FROM users")
    data = cur.fetchall()

    txt = "\n".join(str(u[0]) for u in data[:20])
    await q.message.edit_text(txt, reply_markup=admin_kb())

async def broadcast(update, context):
    if not is_admin(context): return
    q = update.callback_query
    await q.answer()
    context.user_data["broadcast"] = True
    await q.message.reply_text("Send broadcast msg")

async def force(update, context):
    if not is_admin(context): return
    q = update.callback_query
    await q.answer()
    context.user_data["force"] = True
    await q.message.reply_text("Send force msg")

async def ban(update, context):
    if not is_admin(context): return
    q = update.callback_query
    await q.answer()
    context.user_data["ban"] = True
    await q.message.reply_text("Send user id")

async def reset(update, context):
    if not is_admin(context): return
    q = update.callback_query
    await q.answer()

    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM seen")
    db.commit()

    await q.message.edit_text("💀 RESET DONE", reply_markup=admin_kb())

async def logout(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data["is_admin"] = False
    await q.message.edit_text("🔒 Logout")

async def logs(update, context):
    q = update.callback_query
    await q.answer()

    cur.execute("SELECT * FROM logs ORDER BY ROWID DESC LIMIT 10")
    data = cur.fetchall()

    txt = "\n".join(f"{d[0]} → {d[1]}" for d in data)
    await q.message.edit_text(txt)

# ================= MAIN =================
def main():
    global session
    session = aiohttp.ClientSession()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(inbox, pattern="inbox"))
    app.add_handler(CallbackQueryHandler(refresh, pattern="refresh"))
    app.add_handler(CallbackQueryHandler(new, pattern="new"))
    app.add_handler(CallbackQueryHandler(boost, pattern="boost"))
    app.add_handler(CallbackQueryHandler(logs, pattern="logs"))

    app.add_handler(CallbackQueryHandler(admin_login, pattern="admin_login"))
    app.add_handler(CallbackQueryHandler(stats, pattern="stats"))
    app.add_handler(CallbackQueryHandler(users, pattern="users"))
    app.add_handler(CallbackQueryHandler(broadcast, pattern="broadcast"))
    app.add_handler(CallbackQueryHandler(force, pattern="force"))
    app.add_handler(CallbackQueryHandler(ban, pattern="ban"))
    app.add_handler(CallbackQueryHandler(reset, pattern="reset"))
    app.add_handler(CallbackQueryHandler(logout, pattern="logout"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    app.job_queue.run_repeating(global_notify, 4)

    print("🔥 FULL POWER SYSTEM RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
