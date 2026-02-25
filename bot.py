import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, validate_config
from handlers.user_flow import (
    LIST, FILTER, DATE_PICK, TIME_PICK, LANG_PICK, LEVEL_PICK, PHONE, EMAIL, CONFIRM,
    start, tz_cmd, mainmenu_click,
    list_click, filter_click, date_click, time_click, lang_click, level_click,
    phone_input, email_input, confirm_click,
)
from handlers.admin import confirm_cmd, decline_cmd

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("chessflow-bot")

def main():
    validate_config()

    app = Application.builder().token(BOT_TOKEN).build()

    # Global main menu button (works from anywhere)
    app.add_handler(CallbackQueryHandler(mainmenu_click, pattern="^mainmenu$"))

    # Commands
    app.add_handler(CommandHandler("tz", tz_cmd))
    app.add_handler(CommandHandler("confirm", confirm_cmd))
    app.add_handler(CommandHandler("decline", decline_cmd))

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LIST: [CallbackQueryHandler(list_click)],
            FILTER: [CallbackQueryHandler(filter_click)],
            DATE_PICK: [CallbackQueryHandler(date_click)],
            TIME_PICK: [CallbackQueryHandler(time_click)],
            LANG_PICK: [CallbackQueryHandler(lang_click)],
            LEVEL_PICK: [CallbackQueryHandler(level_click)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_input)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_input)],
            CONFIRM: [CallbackQueryHandler(confirm_click)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
        per_message=True,  # removes PTB warning + better callback tracking
    )
    app.add_handler(conv)

    print("Bot running... Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()