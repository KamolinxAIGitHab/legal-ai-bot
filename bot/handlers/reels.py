from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
import os
import logging

from bot.utils.downloader import download_reels_audio
from bot.utils.stt import transcribe_audio
from bot.utils.analyzer import analyze_content

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Assalomu alaykum! Menga Instagram Reel havolasini yuboring, "
        "men uni tahlil qilib, g'oya foydali yoki yo'qligini aytib beraman."
    )

@router.message(F.text.contains("instagram.com/reels/") | F.text.contains("instagram.com/reel/"))
async def handle_reel(message: Message):
    url = message.text.strip()
    status_msg = await message.answer("Video yuklab olinmoqda...")

    try:
        # Download
        file_path = download_reels_audio(url)
        await status_msg.edit_text("Ovoz tekstga aylantirilmoqda...")

        # Transcribe
        text = transcribe_audio(file_path)

        # Clean up file
        if os.path.exists(file_path):
            os.remove(file_path)

        await status_msg.edit_text("Tahlil qilinmoqda...")

        # Analyze
        analysis = analyze_content(text)

        # Handle long messages
        full_response = f"📝 **Transkripsiya:**\n{text}\n\n🔍 **Tahlil:**\n{analysis}"

        if len(full_response) > 4000:
            # Simple split if too long
            await status_msg.edit_text(full_response[:4000])
            await message.answer(full_response[4000:])
        else:
            await status_msg.edit_text(full_response)

    except Exception as e:
        logging.error(f"Error handling reel: {e}")
        await status_msg.edit_text(f"Xatolik yuz berdi: {str(e)}")
    finally:
        # Final cleanup attempt
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

@router.message()
async def echo_all(message: Message):
    await message.answer("Iltimos, Instagram Reel havolasini yuboring.")
