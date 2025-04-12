import re, time, asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked
from motor.motor_asyncio import AsyncIOMotorClient
from info import API_ID, API_HASH, BOT_TOKEN, CLONE_DATABASE_URI, DATABASE_NAME

# ======================== DATABASE CLASSES ========================
class MainDatabase:
    def __init__(self):
        self.client = AsyncIOMotorClient(CLONE_DATABASE_URI)
        self.db = self.client[DATABASE_NAME]
        self.bots = self.db.clone_bots

    async def add_bot(self, bot_id, user_id, bot_token, db_url, db_name, collection):
        await self.bots.insert_one({
            "bot_id": bot_id,
            "user_id": user_id,
            "bot_token": bot_token,
            "db_url": db_url,
            "db_name": db_name,
            "collection": collection
        })

    async def delete_bot(self, bot_id):
        await self.bots.delete_one({"bot_id": bot_id})

    async def get_user_bots(self, user_id):
        return self.bots.find({"user_id": user_id})

    async def get_bot(self, bot_id):
        return await self.bots.find_one({"bot_id": bot_id})

class UserDatabase:
    def __init__(self, db_url, db_name):
        self.client = AsyncIOMotorClient(db_url)
        self.db = self.client[db_name]

    async def get_users(self, collection):
        return self.db[collection].find({})

# Initialize databases
main_db = MainDatabase()

# ======================== BOT CLIENT ========================
app = Client("bot_clone", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ------------------------ ADD BOT ------------------------
@app.on_message(filters.command("addbot") & filters.private)
async def add_bot_handler(client, message):
    user_id = message.from_user.id
    step = await client.ask(user_id, "🔑 Forward your bot token from @BotFather or /cancel")
    
    if step.text == "/cancel":
        return await step.reply("❌ Cancelled!")
    
    if not (step.forward_from and step.forward_from.id == 93372553):  # @BotFather's ID
        return await step.reply("⚠️ Forward directly from @BotFather!")
    
    try:
        bot_token = re.findall(r"\d+:[A-Za-z0-9_-]+", step.text)[0]
    except:
        return await step.reply("❌ Invalid token format!")

    # Get DB details
    db_step = await client.ask(
        user_id, 
        "🗃️ Send DB details:\n`MONGODB_URL | DB_NAME | COLLECTION`",
        filters=filters.text
    )
    
    try:
        db_url, db_name, collection = map(str.strip, db_step.text.split("|"))
    except:
        return await db_step.reply("❌ Use format: `URL | DB_NAME | COLLECTION`")

    # Save bot
    try:
        temp_bot = Client("temp_bot", API_ID, API_HASH, bot_token=bot_token)
        await temp_bot.start()
        bot = await temp_bot.get_me()
        
        await main_db.add_bot(
            bot_id=bot.id,
            user_id=user_id,
            bot_token=bot_token,
            db_url=db_url,
            db_name=db_name,
            collection=collection
        )
        
        await message.reply(f"✅ Bot added!\nUsername: @{bot.username}")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")
    finally:
        if 'temp_bot' in locals():
            await temp_bot.stop()

# ------------------------ DELETE BOT ------------------------
@app.on_message(filters.command("deletebot") & filters.private)
async def delete_bot_handler(client, message):
    user_id = message.from_user.id
    bots = [bot async for bot in main_db.get_user_bots(user_id)]
    
    if not bots:
        return await message.reply("❌ No bots found!")
    
    buttons = [
        [InlineKeyboardButton(f"Bot {idx+1}", callback_data=f"del_{bot['bot_id']}")]
        for idx, bot in enumerate(bots)
    ]
    
    await message.reply(
        "🗑 Select bot to delete:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex("^del_"))
async def delete_callback(client, callback):
    bot_id = int(callback.data.split("_")[1])
    await main_db.delete_bot(bot_id)
    await callback.message.edit_text("✅ Bot deleted!")

# ------------------------ BROADCAST ------------------------
@app.on_message(filters.command("botsbroadcast") & filters.private)
async def broadcast_handler(client, message):
    user_id = message.from_user.id
    bots = [bot async for bot in main_db.get_user_bots(user_id)]
    
    if not bots:
        return await message.reply("❌ No bots found! Add with /addbot")
    
    buttons = [
        [InlineKeyboardButton(f"Bot {idx+1}", callback_data=f"bc_{bot['bot_id']}")]
        for idx, bot in enumerate(bots)
    ]
    
    await message.reply(
        "📢 Select bots to broadcast:",
        reply_markup=InlineKeyboardMarkup(buttons + [
            [InlineKeyboardButton("All Bots", callback_data="bc_all")]
        ])
    )

@app.on_callback_query(filters.regex("^bc_"))
async def broadcast_callback(client, callback):
    bot_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    if bot_id == "all":
        bots = [bot async for bot in main_db.get_user_bots(user_id)]
    else:
        bots = [await main_db.get_bot(int(bot_id))]
    
    msg = await client.ask(user_id, "📝 Enter broadcast message:")
    
    for bot in bots:
        user_db = UserDatabase(bot["db_url"], bot["db_name"])
        users = await user_db.get_users(bot["collection"])
        
        success = failed = 0
        async for user in users:
            try:
                async with Client("bc_client", API_ID, API_HASH, bot_token=bot["bot_token"]) as bc_bot:
                    await bc_bot.send_message(user["user_id"], msg.text)
                    success += 1
            except Exception:
                failed += 1
        
        await callback.message.reply(
            f"📊 Report for bot ID {bot['bot_id']}:\n"
            f"✅ Success: {success}\n"
            f"❌ Failed: {failed}"
            )
