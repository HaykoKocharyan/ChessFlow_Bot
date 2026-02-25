from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_CHAT_ID

def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_CHAT_ID

async def confirm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /confirm <student_id> <ziina_link>")
        return

    try:
        student_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("student_id must be a number.")
        return

    ziina_link = context.args[1].strip()

    msg = (
        "✅ Booking confirmed!\n\n"
        "Your tutor is available. Please proceed to payment using the link below:\n"
        f"{ziina_link}\n\n"
        "After payment, we will share the meeting details."
    )

    try:
        await context.bot.send_message(chat_id=student_id, text=msg, disable_web_page_preview=True)
        await update.message.reply_text("Sent confirmation + payment link to student.")
    except Exception as e:
        await update.message.reply_text(f"Failed to message student: {e}")

async def decline_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /decline <student_id> <message...>")
        return

    try:
        student_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("student_id must be a number.")
        return

    reason = " ".join(context.args[1:]).strip()
    msg = (
        "❌ Booking not confirmed\n\n"
        f"{reason}\n\n"
        "Tap Main menu to choose another tutor/time."
    )

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main menu", callback_data="mainmenu")]])

    try:
        await context.bot.send_message(chat_id=student_id, text=msg, reply_markup=markup)
        await update.message.reply_text("Sent decline message to student (with Main menu button).")
    except Exception as e:
        await update.message.reply_text(f"Failed to message student: {e}")