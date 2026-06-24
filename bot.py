import os
import re
import json
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic
import transcription
import database

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
CLAUDE_MODEL = "claude-3-5-sonnet-20240620"

L = {
    "lang_uz_cyr": {
        "start": "Ассалому алайкум! Мен шахсий ёрдамчиман. Харажатлар, вазифалар ёки қайдларни овозли хабар орқали юборинг.",
        "chosen": "✅ Тил танланди! Энди овозли хабар юборишингиз мумкин.",
        "wait": "⏳ Илтимос, кутинг...",
        "transcribing": "🎤 Овоз матнга айлантирилмоқда...",
        "analyzing": "🧠 Маълумот таҳлил қилинмоқда...",
        "done": "✅ Сақланди!",
        "err_voice": "❌ Овозни тушуниб бўлмади.",
        "err_api": "❌ Ташқи хизматда хатолик.",
        "disclaimer": "⚠️ Маълумотлар автоматик таҳлил қилинди.",
        "list_title": "📋 Сўнгги қайдлар:",
        "stats_title": "📊 Статистика:",
        "empty": "📭 Ҳеч нарса топилмади."
    },
    "lang_uz_lat": {
        "start": "Assalomu alaykum! Men shaxsiy yordamchiman. Xarajatlar, vazifalar yoki qaydlarni ovozli xabar orqali yuboring.",
        "chosen": "✅ Til tanlandi! Endi ovozli xabar yuborishingiz mumkin.",
        "wait": "⏳ Iltimos, kuting...",
        "transcribing": "🎤 Ovoz matnga aylantirilmoqda...",
        "analyzing": "🧠 Ma'lumot tahlil qilinmoqda...",
        "done": "✅ Saqlandi!",
        "err_voice": "❌ Ovozni tushunib bo'lmadi.",
        "err_api": "❌ Tashqi xizmatda xatolik.",
        "disclaimer": "⚠️ Ma'lumotlar avtomatik tahlil qilindi.",
        "list_title": "📋 So'nggi qaydlar:",
        "stats_title": "📊 Statistika:",
        "empty": "📭 Hech narsa topilmadi."
    },
    "lang_ru": {
        "start": "Здравствуйте! Я личный помощник. Отправляйте расходы, задачи или заметки голосовым сообщением.",
        "chosen": "✅ Язык выбран! Теперь вы можете отправлять голосовые сообщения.",
        "wait": "⏳ Пожалуйста, подождите...",
        "transcribing": "🎤 Расшифровка голоса...",
        "analyzing": "🧠 Анализ данных...",
        "done": "✅ Сохранено!",
        "err_voice": "❌ Не удалось распознать голос.",
        "err_api": "❌ Ошибка внешнего сервиса.",
        "disclaimer": "⚠️ Данные проанализированы автоматически.",
        "list_title": "📋 Последние записи:",
        "stats_title": "📊 Статистика:",
        "empty": "📭 Ничего не найдено."
    }
}

SYSTEM_PROMPT = """You are a trilingual (Uzbek Cyrillic, Uzbek Latin, Russian) life logger assistant.
Extract data from user text and return strictly JSON.
Fields:
- entry_type: "expense", "task", or "note"
- amount: float (for expenses, else null)
- currency: "UZS", "USD", etc. (for expenses, else null)
- category: short category name
- content: cleaned description

Text examples:
"Бугун тушликка 50 минг сўм ишлатдим" -> {"entry_type": "expense", "amount": 50000, "currency": "UZS", "category": "food", "content": "Lunch"}
"Эртага соат 10да учрашув" -> {"entry_type": "task", "amount": null, "currency": null, "category": "meeting", "content": "Meeting at 10:00"}
"Нон олиш керак" -> {"entry_type": "note", "amount": null, "currency": null, "category": "shopping", "content": "Buy bread"}"""

def extract_json(text):
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    return text.strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(
        "Илтимос, тилни танланг / Iltimos, tilni tanlang / Пожалуйста, выберите язык:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    await query.edit_message_text(L[lang]["chosen"])

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    status_msg = await update.message.reply_text(L[lang]["wait"])

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await status_msg.edit_text(L[lang]["transcribing"])

        voice_file = await update.message.voice.get_file()
        ogg_path = f"voice_{update.message.message_id}.ogg"
        await voice_file.download_to_drive(ogg_path)

        text = transcription.process_voice(ogg_path, lang)
        if os.path.exists(ogg_path):
            os.remove(ogg_path)

        if not text:
            await status_msg.edit_text(L[lang]["err_voice"])
            return

        await status_msg.edit_text(L[lang]["analyzing"])
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}]
        )

        raw_json = extract_json(message.content[0].text)
        data = json.loads(raw_json)
        database.add_entry(
            user_id=update.effective_user.id,
            entry_type=data.get("entry_type"),
            raw_text=text,
            amount=data.get("amount"),
            currency=data.get("currency"),
            category=data.get("category"),
            content=data.get("content")
        )

        response = f"📝: {text}\n\n{L[lang]['done']}\n"
        if data.get("entry_type") == "expense":
            response += f"💰 {data.get('amount')} {data.get('currency')}"

        await status_msg.edit_text(response)

    except Exception as e:
        print(f"Error: {e}")
        await status_msg.edit_text(L[lang]["err_api"])

async def list_entries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    entries = database.get_entries(update.effective_user.id)

    if not entries:
        await update.message.reply_text(L[lang]["empty"])
        return

    text = f"{L[lang]['list_title']}\n\n"
    for e_type, amt, curr, cont, date in entries:
        icon = "💰" if e_type == "expense" else "✅" if e_type == "task" else "📝"
        val = f" - {amt} {curr}" if amt else ""
        text += f"{icon} {cont}{val} ({date[:10]})\n"

    await update.message.reply_text(text)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    stats = database.get_stats(update.effective_user.id)

    if not stats:
        await update.message.reply_text(L[lang]["empty"])
        return

    text = f"{L[lang]['stats_title']}\n\n"
    for e_type, count, total_amt, curr in stats:
        icon = "💰" if e_type == "expense" else "✅" if e_type == "task" else "📝"
        amt_str = f": {total_amt} {curr}" if total_amt else ""
        text += f"{icon} {e_type.capitalize()}: {count}{amt_str}\n"

    await update.message.reply_text(text)

def main():
    database.init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_entries))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
