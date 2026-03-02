"""管理员命令处理器"""
import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_USER_ID
from database_mysql import Database
from utils.checks import reject_group_command

logger = logging.getLogger(__name__)


async def addbalance_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /addbalance 命令 - 管理员增加积分"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "使用方法: /addbalance <用户ID> <积分数量>\n\n示例: /addbalance 123456789 10"
        )
        return

    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])

        if not db.user_exists(target_user_id):
            await update.message.reply_text("User not found.")
            return

        if db.add_balance(target_user_id, amount):
            user = db.get_user(target_user_id)
            await update.message.reply_text(
                f"✅ Added ${2} points to user ${1}.\n"
                f"Current points: {user['balance']}"
            )
        else:
            await update.message.reply_text("Operation failed. Please try again later.")
    except ValueError:
        await update.message.reply_text("Invalid arguments. Please enter valid numbers.")


async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /block 命令 - 管理员拉黑用户"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    if not context.args:
        await update.message.reply_text(
            "使用方法: /block <用户ID>\n\n示例: /block 123456789"
        )
        return

    try:
        target_user_id = int(context.args[0])

        if not db.user_exists(target_user_id):
            await update.message.reply_text("User not found.")
            return

        if db.block_user(target_user_id):
            await update.message.reply_text(f"✅ User ${1} has been blocked.")
        else:
            await update.message.reply_text("Operation failed. Please try again later.")
    except ValueError:
        await update.message.reply_text("Invalid argument format. Please provide a valid user ID.")


async def white_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /white 命令 - 管理员取消拉黑"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    if not context.args:
        await update.message.reply_text(
            "使用方法: /white <用户ID>\n\n示例: /white 123456789"
        )
        return

    try:
        target_user_id = int(context.args[0])

        if not db.user_exists(target_user_id):
            await update.message.reply_text("User not found.")
            return

        if db.unblock_user(target_user_id):
            await update.message.reply_text(f"✅ User ${1} has been removed from blacklist.")
        else:
            await update.message.reply_text("Operation failed. Please try again later.")
    except ValueError:
        await update.message.reply_text("Invalid argument format. Please provide a valid user ID.")


async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /blacklist 命令 - 查看黑名单"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    blacklist = db.get_blacklist()

    if not blacklist:
        await update.message.reply_text("Blacklist is empty.")
        return

    msg = "📋 Blacklist:\n\n"
    for user in blacklist:
        msg += f"User ID: {user['user_id']}\n"
        msg += f"Username: @{user['username']}\n"
        msg += f"Name: {user['full_name']}\n"
        msg += "---\n"

    await update.message.reply_text(msg)


async def genkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /genkey 命令 - 管理员生成卡密"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "使用方法: /genkey <卡密> <积分> [使用次数] [过期 days数]\n\n"
            "示例:\n"
            "/genkey wandouyu 20 - 生成20积分的卡密（单次使用，永不过期）\n"
            "/genkey vip100 50 10 - 生成50积分的卡密（可使用10次，永不过期）\n"
            "/genkey temp 30 1 7 - 生成30积分的卡密（单次使用，7 days后过期）"
        )
        return

    try:
        key_code = context.args[0].strip()
        balance = int(context.args[1])
        max_uses = int(context.args[2]) if len(context.args) > 2 else 1
        expire_days = int(context.args[3]) if len(context.args) > 3 else None

        if balance <= 0:
            await update.message.reply_text("Points must be greater than 0.")
            return

        if max_uses <= 0:
            await update.message.reply_text("Max uses must be greater than 0.")
            return

        if db.create_card_key(key_code, balance, user_id, max_uses, expire_days):
            msg = (
                "✅ Card key created successfully!\n\n"
                f"Code: {key_code}\n"
                f"Points: {balance}\n"
                f"Uses: {max_uses}次\n"
            )
            if expire_days:
                msg += f"Validity: {expire_days} days\n"
            else:
                msg += "Validity: Permanent\n"
            msg += f"\nUser command: /use {key_code}"
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("Key already exists or creation failed. Please choose another key name.")
    except ValueError:
        await update.message.reply_text("Invalid arguments. Please enter valid numbers.")


async def listkeys_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /listkeys 命令 - 管理员查看卡密列表"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    keys = db.get_all_card_keys()

    if not keys:
        await update.message.reply_text("No card keys found.")
        return

    msg = "📋 Card Keys:\n\n"
    for key in keys[:20]:  # 只显示前20个
        msg += f"Code: {key['key_code']}\n"
        msg += f"Points: {key['balance']}\n"
        msg += f"Uses: {key['current_uses']}/{key['max_uses']}\n"

        if key["expire_at"]:
            expire_time = datetime.fromisoformat(key["expire_at"])
            if datetime.now() > expire_time:
                msg += "Status: Expired\n"
            else:
                days_left = (expire_time - datetime.now()).days
                msg += f"状态：有效（剩余{days_left} days）\n"
        else:
            msg += "状态：Permanent有效\n"

        msg += "---\n"

    if len(keys) > 20:
        msg += f"\n(Showing first 20 only, total: ${1})"

    await update.message.reply_text(msg)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /broadcast 命令 - 管理员群发通知"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    text = " ".join(context.args).strip() if context.args else ""
    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text or ""

    if not text:
        await update.message.reply_text("Usage: /broadcast <text>, or reply to a message then send /broadcast")
        return

    user_ids = db.get_all_user_ids()
    success, failed = 0, 0

    status_msg = await update.message.reply_text(f"📢 Broadcast started, total users: ${1}...")

    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            success += 1
            await asyncio.sleep(0.05)  # 适当限速避免触发限制
        except Exception as e:
            logger.warning("广播到 %s 失败: %s", uid, e)
            failed += 1

    await status_msg.edit_text(f"✅ 广播完成！\n成功：{success}\n失败：{failed}")
