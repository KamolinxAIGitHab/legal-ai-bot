import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from bot.config import settings
from bot.handlers import reels

async def main():
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    dp.include_router(reels.router)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")
    except Exception as e:
        print(f"Error: {e}")
