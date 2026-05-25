import logging
import os
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from dotenv import load_dotenv

from src.handlers.commands import (
    cmd_new, cmd_join, cmd_start_game, cmd_leave, cmd_close, cmd_open,
    cmd_kill, cmd_kick, cmd_skip, cmd_help, cmd_stats, cmd_pemilik
)
from src.handlers.callbacks import handle_callback

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN tidak ditemukan di environment variables!")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("join", cmd_join))
    app.add_handler(CommandHandler("start", cmd_start_game))
    app.add_handler(CommandHandler("leave", cmd_leave))
    app.add_handler(CommandHandler("close", cmd_close))
    app.add_handler(CommandHandler("open", cmd_open))
    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("pemilik", cmd_pemilik))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot UNO berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
