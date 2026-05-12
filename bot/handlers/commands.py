from aiogram import Router, types
from aiogram.filters import Command

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Ассалому алайкум! Юридик СИ ботга хуш келибсиз. Саволингизни беришингиз мумкин.")
