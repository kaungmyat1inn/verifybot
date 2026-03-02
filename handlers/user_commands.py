"""用户命令处理器"""
import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_USER_ID
from database_mysql import Database
from utils.checks import reject_group_command
from utils.messages import (
    get_welcome_message,
    get_about_message,
    get_help_message,
)

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /start 命令"""
    if await reject_group_command(update):
        return

    user = update.effective_user
    user_id = user.id
    username = user.username or ""
    full_name = user.full_name or ""

    # 已初始化直接返回
    if db.user_exists(user_id):
        await update.message.reply_text(
            f"Welcome back, {full_name}!\n"
            "Your account is already initialized.\n"
            "Send /help to view available commands."
        )
        return

    # 邀请参与
    invited_by: Optional[int] = None
    if context.args:
        try:
            invited_by = int(context.args[0])
            if not db.user_exists(invited_by):
                invited_by = None
        except Exception:
            invited_by = None

    # 创建用户
    if db.create_user(user_id, username, full_name, invited_by):
        welcome_msg = get_welcome_message(full_name, bool(invited_by))
        await update.message.reply_text(welcome_msg)
    else:
        await update.message.reply_text("Registration failed. Please try again later.")


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /about 命令"""
    if await reject_group_command(update):
        return

    await update.message.reply_text(get_about_message())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /help 命令"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_USER_ID
    await update.message.reply_text(get_help_message(is_admin))


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /balance 命令"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if db.is_user_blocked(user_id):
        await update.message.reply_text("You are blocked and cannot use this feature.")
        return

    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Please register first using /start.")
        return

    await update.message.reply_text(
        f"💰 积分余额\n\nCurrent points: {user['balance']}"
    )


async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /qd 签到命令 - 临时禁用"""
    user_id = update.effective_user.id

    # 临时禁用签到功能（修复bug中）
    # await update.message.reply_text(
    #     "⚠️ 签到功能临时维护中\n\n"
    #     "由于发现bug，签到功能暂时关闭，正在修复。\n"
    #     "预计很快恢复，给您带来不便敬请谅解。\n\n"
    #     "💡 您可以通过以下方式获取积分：\n"
    #     "• 邀请好友 /invite（+2积分）\n"
    #     "• 使用卡密 /use <卡密>"
    # )
    # return
    
    # ===== 以下代码已禁用 =====
    if db.is_user_blocked(user_id):
        await update.message.reply_text("You are blocked and cannot use this feature.")
        return

    if not db.user_exists(user_id):
        await update.message.reply_text("Please register first using /start.")
        return

    # 第1层检查：在命令处理器层面检查
    if not db.can_checkin(user_id):
        await update.message.reply_text("❌ You have already checked in today. Please come back tomorrow.")
        return

    # 第2层检查：在数据库层面执行（SQL原子操作）
    if db.checkin(user_id):
        user = db.get_user(user_id)
        await update.message.reply_text(
            f"✅ 签到成功！\n获得积分：+1\nCurrent points: {user['balance']}"
        )
    else:
        # 如果数据库层面返回False，说明今天已签到（双重保险）
        await update.message.reply_text("❌ You have already checked in today. Please come back tomorrow.")


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /invite 邀请命令"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if db.is_user_blocked(user_id):
        await update.message.reply_text("You are blocked and cannot use this feature.")
        return

    if not db.user_exists(user_id):
        await update.message.reply_text("Please register first using /start.")
        return

    bot_username = context.bot.username
    invite_link = f"https://t.me/{bot_username}?start={user_id}"

    await update.message.reply_text(
        f"🎁 您的专属邀请链接：\n{invite_link}\n\n"
        "You earn 2 points for each successful referral."
    )


async def use_command(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database):
    """处理 /use 命令 - 使用卡密"""
    if await reject_group_command(update):
        return

    user_id = update.effective_user.id

    if db.is_user_blocked(user_id):
        await update.message.reply_text("You are blocked and cannot use this feature.")
        return

    if not db.user_exists(user_id):
        await update.message.reply_text("Please register first using /start.")
        return

    if not context.args:
        await update.message.reply_text(
            "使用方法: /use <卡密>\n\n示例: /use wandouyu"
        )
        return

    key_code = context.args[0].strip()
    result = db.use_card_key(key_code, user_id)

    if result is None:
        await update.message.reply_text("Card key not found. Please check and try again.")
    elif result == -1:
        await update.message.reply_text("This card key has reached its usage limit.")
    elif result == -2:
        await update.message.reply_text("This card key has expired.")
    elif result == -3:
        await update.message.reply_text("You have already used this card key.")
    else:
        user = db.get_user(user_id)
        await update.message.reply_text(
            f"卡密使用成功！\n获得积分：{result}\nCurrent points: {user['balance']}"
        )
