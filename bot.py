import re
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pymongo import MongoClient

# ==== CONFIG ====
BOT_TOKEN = "7643831340:AAGieuPJND4MekAutSf3xzta1qdoKo5mbZU"
MONGO_URI = "mongodb+srv://afzal99550:afzal99550@cluster0.aqmbh9q.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
LOG_CHANNEL_ID = -1002821784807
OWNER_IDS = [6998916494]  # Only one owner

# ==== MONGO CONNECT ====
client = MongoClient(MONGO_URI)
db = client["escrow_bot"]
groups_col = db["groups"]
global_col = db["global"]
admins_col = db["admins"]

# Ensure global doc exists
if not global_col.find_one({"_id": "stats"}):
    global_col.insert_one({
        "_id": "stats",
        "total_deals": 0,
        "total_volume": 0,
        "total_fee": 0.0,
        "escrowers": {}
    })

# ==== HELPERS ====
async def is_admin(update: Update) -> bool:
    user_id = update.effective_user.id
    if user_id in OWNER_IDS:
        return True
    return admins_col.find_one({"user_id": user_id}) is not None

def init_group(chat_id: str):
    if not groups_col.find_one({"_id": chat_id}):
        groups_col.insert_one({
            "_id": chat_id,
            "deals": {},
            "total_deals": 0,
            "total_volume": 0,
            "total_fee": 0.0,
            "escrowers": {}
        })

def update_escrower_stats(group_id: str, escrower: str, amount: float):
    g = groups_col.find_one({"_id": group_id})
    g["total_deals"] += 1
    g["total_volume"] += amount
    g["escrowers"][escrower] = g["escrowers"].get(escrower, 0) + amount
    groups_col.update_one({"_id": group_id}, {"$set": g})

    global_data = global_col.find_one({"_id": "stats"})
    global_data["total_deals"] += 1
    global_data["total_volume"] += amount
    global_data["escrowers"][escrower] = global_data["escrowers"].get(escrower, 0) + amount
    global_col.update_one({"_id": "stats"}, {"$set": global_data})

# ==== COMMANDS ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "✨ <b>Welcome to Escrower Bot!</b> ✨\n\n"
        "• /add <code>amount</code> – Add a new deal\n"
        "• /complete <code>amount</code> – Complete a deal\n"
        "• /status <code>trade_id</code> – Check deal status by Trade ID\n"
        "• /stats – Your personal stats\n"
        "• /gstats – Global stats (Admin only)\n"
        "• /estats – Escrower performance stats (Admin only)\n"
        "• /addadmin <code>user_id</code> – Owner only\n"
        "• /removeadmin <code>user_id</code> – Owner only\n"
        "• /adminlist – Show all admins"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

async def add_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    try:
        await update.message.delete()
    except:
        pass
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Reply to the DEAL INFO message!")

    if not context.args or not context.args[0].replace(".", "", 1).isdigit():
        return await update.message.reply_text("❌ Please provide amount like /add 50")

    amount = float(context.args[0])
    original_text = update.message.reply_to_message.text
    chat_id = str(update.effective_chat.id)
    reply_id = str(update.message.reply_to_message.message_id)
    init_group(chat_id)

    buyer_match = re.search(r"BUYER\s*:\s*(@\w+)", original_text, re.IGNORECASE)
    seller_match = re.search(r"SELLER\s*:\s*(@\w+)", original_text, re.IGNORECASE)
    buyer = buyer_match.group(1).strip() if buyer_match else "Unknown"
    seller = seller_match.group(1).strip() if seller_match else "Unknown"

    g = groups_col.find_one({"_id": chat_id})
    deals = g["deals"]
    trade_id = f"TID{random.randint(100000, 999999)}"
    deals[reply_id] = {
        "trade_id": trade_id,
        "added_amount": amount,
        "completed": False,
        "buyer": buyer,
        "seller": seller,
        "escrower": f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.full_name
    }
    g["deals"] = deals
    groups_col.update_one({"_id": chat_id}, {"$set": g})

    escrower = deals[reply_id]["escrower"]
    update_escrower_stats(chat_id, escrower, amount)

    msg = (
        f"✅ <b>Amount Received!</b>\n"
        "────────────────\n"
        f"👤 Buyer : {buyer}\n"
        f"👤 Seller : {seller}\n"
        f"💰 Amount : ₹{amount}\n"
        f"🆔 Trade ID : #{trade_id}\n"
        "────────────────\n"
        f"🛡️ Escrowed by {escrower}"
    )
    await update.effective_chat.send_message(msg, reply_to_message_id=update.message.reply_to_message.message_id, parse_mode="HTML")

async def complete_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    try:
        await update.message.delete()
    except:
        pass
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Reply to the DEAL INFO message!")

    if not context.args or not context.args[0].replace(".", "", 1).isdigit():
        return await update.message.reply_text("❌ Please provide amount like /complete 50")

    released = float(context.args[0])
    chat_id = str(update.effective_chat.id)
    reply_id = str(update.message.reply_to_message.message_id)
    g = groups_col.find_one({"_id": chat_id})
    deal_info = g["deals"].get(reply_id)

    if not deal_info:
        return await update.message.reply_text("❌ Deal not found!")
    if deal_info["completed"]:
        return await update.message.reply_text("⚠️ Already completed!")

    deal_info["completed"] = True
    g["deals"][reply_id] = deal_info

    added_amount = deal_info["added_amount"]
    fee = added_amount - released if added_amount > released else 0
    g["total_fee"] += fee
    groups_col.update_one({"_id": chat_id}, {"$set": g})

    global_data = global_col.find_one({"_id": "stats"})
    global_data["total_fee"] += fee
    global_col.update_one({"_id": "stats"}, {"$set": global_data})

    buyer = deal_info.get("buyer", "Unknown")
    seller = deal_info.get("seller", "Unknown")
    escrower = deal_info.get("escrower", "Unknown")
    trade_id = deal_info["trade_id"]

    msg = (
        f"✅ <b>Deal Completed!</b>\n"
        "────────────────\n"
        f"👤 Buyer  : {buyer}\n"
        f"👤 Seller  : {seller}\n"
        f"💸 Released : ₹{released}\n"
        f"🆔 Trade ID : #{trade_id}\n"
        f"💰 Fee     : ₹{fee}\n"
        "────────────────\n"
        f"🛡️ Escrowed by {escrower}"
    )
    await update.effective_chat.send_message(msg, reply_to_message_id=update.message.reply_to_message.message_id, parse_mode="HTML")

    log_msg = (
        "📜 <b>Deal Completed (Log)</b>\n"
        "────────────────\n"
        f"👤 Buyer   : {buyer}\n"
        f"👤 Seller  : {seller}\n"
        f"💸 Released: ₹{released}\n"
        f"🆔 Trade ID: #{trade_id}\n"
        f"💰 Fee     : ₹{fee}\n"
        f"🛡️ Escrowed by {escrower}\n"
        f"📌 Group: {update.effective_chat.title} ({update.effective_chat.id})"
    )
    await context.bot.send_message(LOG_CHANNEL_ID, log_msg, parse_mode="HTML")

async def deal_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Usage: /status <trade_id>")
    trade_id = context.args[0].strip().replace("#", "").upper()
    found = None
    for g in groups_col.find({}):
        for deal in g.get("deals", {}).values():
            if deal and deal.get("trade_id", "").upper() == trade_id:
                found = deal
                break
        if found:
            break
    if not found:
        return await update.message.reply_text("⚠️ No deal found with this Trade ID!")
    status = "✅ Completed" if found.get("completed") else "⌛ Pending"
    msg = (
        f"📌 <b>Deal Status</b>\n"
        f"🆔 Trade ID: #{found.get('trade_id')}\n"
        f"👤 Buyer: {found.get('buyer', 'Unknown')}\n"
        f"👤 Seller: {found.get('seller', 'Unknown')}\n"
        f"💰 Amount: ₹{found.get('added_amount', 0)}\n"
        f"📊 Status: {status}"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

async def global_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    g = global_col.find_one({"_id": "stats"})
    escrowers_text = "\n".join([f"{name} = ₹{amt}" for name, amt in g["escrowers"].items()]) or "No deals yet"
    msg = (
        f"🌍 Global Stats\n\n"
        f"{escrowers_text}\n\n"
        f"🔹 Total Deals: {g['total_deals']}\n"
        f"💰 Total Volume: ₹{g['total_volume']}\n"
        f"💸 Total Fee: ₹{g['total_fee']}"
    )
    await update.message.reply_text(msg)

# ==== NEW: ESCROWER STATS (/estats) ====
async def escrow_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.message.reply_text("❌ Only admins/owners can use this command!")

    if context.args:
        escrower = context.args[0].strip().lower()
    else:
        user = update.effective_user
        escrower = f"@{user.username}".lower() if user.username else user.full_name.lower()

    total_deals = 0
    total_volume = 0
    completed = 0
    pending = 0
    total_fee = 0

    for g in groups_col.find({}):
        for deal in g.get("deals", {}).values():
            if not deal or "escrower" not in deal:
                continue
            e = str(deal.get("escrower", "")).lower().strip()
            if e == escrower:
                total_deals += 1
                total_volume += deal.get("added_amount", 0)
                if deal.get("completed"):
                    completed += 1
                else:
                    pending += 1
                added = deal.get("added_amount", 0)
                released = added if deal.get("completed") else 0
                total_fee += max(0, added - released)

    if total_deals == 0:
        return await update.message.reply_text("📊 No deals found for this escrower.")

    msg = (
        f"📊 <b>Escrow Stats for {escrower}</b>\n"
        "────────────────\n"
        f"📦 Total Deals: {total_deals}\n"
        f"💰 Total Volume: ₹{total_volume}\n"
        f"✅ Completed Deals: {completed}\n"
        f"⌛ Pending Deals: {pending}\n"
        f"💸 Total Fee Earned: ₹{total_fee}"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

# ==== STATS ====
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = f"@{user.username}" if user.username else user.full_name
    user_check = username.lower().strip()
    total_deals = 0
    total_volume = 0
    ongoing_deals = 0
    highest_deal = 0
    all_users = {}
    for g in groups_col.find({}):
        for deal in g.get("deals", {}).values():
            if not deal:
                continue
            buyer = str(deal.get("buyer", "")).lower().strip()
            seller = str(deal.get("seller", "")).lower().strip()
            amount = deal.get("added_amount", 0)
            completed = deal.get("completed", False)
            if user_check == buyer or user_check == seller:
                total_deals += 1
                total_volume += amount
                highest_deal = max(highest_deal, amount)
                if not completed:
                    ongoing_deals += 1
            for u in [buyer, seller]:
                if u.startswith("@"):
                    if u not in all_users:
                        all_users[u] = {"volume": 0}
                    all_users[u]["volume"] += amount
    if total_deals == 0:
        return await update.message.reply_text("📊 No deals found for you.")
    sorted_users = sorted(all_users.items(), key=lambda x: x[1]["volume"], reverse=True)
    rank = next((i + 1 for i, (u, _) in enumerate(sorted_users) if u == user_check), "N/A")
    msg = (
        f"📊 <b>Participant Stats for {username}</b>\n\n"
        f"👑 Ranking: {rank}\n"
        f"📈 Total Volume: ₹{total_volume}\n"
        f"🧳 Total Deals: {total_deals}\n"
        f"🧿 Ongoing Deals: {ongoing_deals}\n"
        f"💳 Highest Deal - ₹{highest_deal}"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

# ==== ADMIN COMMANDS ====
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in OWNER_IDS:
        return await update.message.reply_text("❌ Only owners can add admins!")
    if not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("❌ Provide a valid user_id, e.g. /addadmin 123456789")
    new_admin_id = int(context.args[0])
    if admins_col.find_one({"user_id": new_admin_id}):
        return await update.message.reply_text("⚠️ Already an admin!")
    admins_col.insert_one({"user_id": new_admin_id})
    await update.message.reply_text(f"✅ Added as admin: <code>{new_admin_id}</code>", parse_mode="HTML")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in OWNER_IDS:
        return await update.message.reply_text("❌ Only owners can remove admins!")
    if not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("❌ Provide a valid user_id, e.g. /removeadmin 123456789")
    remove_id = int(context.args[0])
    if not admins_col.find_one({"user_id": remove_id}):
        return await update.message.reply_text("⚠️ This user is not an admin!")
    admins_col.delete_one({"user_id": remove_id})
    await update.message.reply_text(f"✅ Removed admin: <code>{remove_id}</code>", parse_mode="HTML")

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    admins = list(admins_col.find({}, {"_id": 0, "user_id": 1}))
    owners = [f"⭐ Owner: <code>{oid}</code>" for oid in OWNER_IDS]
    admins_text = "\n".join([f"👮 Admin: <code>{a['user_id']}</code>" for a in admins]) or "No extra admins added."
    msg = "📋 <b>Admin List</b>\n\n" + "\n".join(owners) + "\n" + admins_text
    await update.message.reply_text(msg, parse_mode="HTML")

# ==== MAIN ====
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_deal))
    app.add_handler(CommandHandler("complete", complete_deal))
    app.add_handler(CommandHandler("status", deal_status))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("gstats", global_stats))
    app.add_handler(CommandHandler("estats", escrow_stats))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("adminlist", admin_list))
    print("Bot started... ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
