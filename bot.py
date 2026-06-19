import os
import re
import json
import database

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from telegram.constants import ChatAction
import anthropic
from openai import OpenAI

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

LOGGING_SYSTEM_PROMPT = """You are a trilingual assistant (Uzbek Cyrillic, Uzbek Latin, Russian) that categorizes and structures personal logs.
Extract information from the text and return a JSON object.
Categories:
- expense: Money spent (amount, currency, item)
- task: Something to do
- note: Information to remember
- reminder: Something for a specific time (if mentioned)

JSON format:
{
  "category": "expense" | "task" | "note" | "reminder",
  "data": { ... relevant fields ... },
  "summary": "Short trilingual summary"
}

If you are not sure, use "note". Return ONLY the JSON object, no other text."""

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "chosen": "✅ Тил танланди!",
        "welcome": "Харажатлар, вазифалар ёки қайдларни ёзинг ёки овозли хабар юборинг:",
        "wait": "⏳ Ишланяпти...",
        "voice_processing": "🎤 Овоз эшитилмоқда...",
        "categorizing": "🧠 Таҳлил қилинмоқда...",
        "saved": "✅ Сақланди: {summary}",
        "history_header": "📜 Охирги қайдларингиз:",
        "stats_empty": "📭 Ҳозирча қайдлар йўқ.",
        "error_api": "❌ API калит топилмади.",
        "error_no_key": "❌ Овозли хабар учун OpenAI API калити созланмаган.",
        "error_gen": "❌ Хатолик юз берди."
    },
    "lang_uz_lat": {
        "chosen": "✅ Til tanlandi!",
        "welcome": "Xarajatlar, vazifalar yoki qaydlarni yozing yoki ovozli xabar yuboring:",
        "wait": "⏳ Ishlanyapti...",
        "voice_processing": "🎤 Ovoz eshitilmoqda...",
        "categorizing": "🧠 Tahlil qilinmoqda...",
        "saved": "✅ Saqlandi: {summary}",
        "history_header": "📜 Oxirgi qaydlaringiz:",
        "stats_empty": "📭 Hozircha qaydlar yo'q.",
        "error_api": "❌ API kalit topilmadi.",
        "error_no_key": "❌ Ovozli xabar uchun OpenAI API kaliti sozlanmagan.",
        "error_gen": "❌ Xatolik yuz berdi."
    },
    "lang_ru": {
        "chosen": "✅ Язык выбран!",
        "welcome": "Запишите расходы, задачи или заметки текстом или голосом:",
        "wait": "⏳ В работе...",
        "voice_processing": "🎤 Слушаю голос...",
        "categorizing": "🧠 Анализирую...",
        "saved": "✅ Сохранено: {summary}",
        "history_header": "📜 Ваши последние записи:",
        "stats_empty": "📭 Записей пока нет.",
        "error_api": "❌ API ключ не найден.",
        "error_no_key": "❌ OpenAI API ключ не настроен для голоса.",
        "error_gen": "❌ Произошла ошибка."
    }
}

def extract_json(text):
    try:
        # Try finding json block
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return json.loads(text)
    except Exception as e:
        print(f"JSON parsing error: {e}")
        return None

async def process_input_text(text, user_id, msgs, status_msg=None):
    if not CLAUDE_API_KEY:
        error_text = msgs["error_api"]
        if status_msg: await status_msg.edit_text(error_text)
        return False

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            system=LOGGING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}]
        )

        result_json = extract_json(message.content[0].text)
        if not result_json:
            result_json = {"category": "note", "summary": text[:50], "data": {}}

        category = result_json.get("category", "note")
        summary = result_json.get("summary", text[:50])

        database.add_log(user_id, category, text, result_json)

        final_text = msgs["saved"].format(summary=summary)
        if status_msg:
            await status_msg.edit_text(final_text)
        return True

    except Exception as e:
        print(f"AI error: {e}")
        error_text = f"🤖 {text}\n\n⚠️ {msgs['error_gen']}"
        if status_msg: await status_msg.edit_text(error_text)
        return False

async def transcribe_voice(file_path):
    if not OPENAI_API_KEY:
        return None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        return transcript.text
    except Exception as e:
        print(f"Transcription error: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(
        "Илтимос, тилни танланг:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    await query.edit_message_text(
        f"{msgs['chosen']}\n\n{msgs['welcome']}"
    )

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    text = update.message.text

    status_msg = await update.message.reply_text(msgs["wait"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    await process_input_text(text, update.effective_user.id, msgs, status_msg)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    if not OPENAI_API_KEY:
        await update.message.reply_text(msgs["error_no_key"])
        return

    status_msg = await update.message.reply_text(msgs["voice_processing"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    voice_file = await update.message.voice.get_file()
    os.makedirs("temp", exist_ok=True)
    file_path = f"temp/{voice_file.file_id}.ogg"
    await voice_file.download_to_drive(file_path)

    text = await transcribe_voice(file_path)
    os.remove(file_path)

    if not text:
        await status_msg.edit_text(msgs["error_gen"])
        return

    await status_msg.edit_text(msgs["categorizing"])
    await process_input_text(text, update.effective_user.id, msgs, status_msg)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    logs = database.get_recent_logs(update.effective_user.id)
    if not logs:
        await update.message.reply_text(msgs["stats_empty"])
        return

    text = f"{msgs['history_header']}\n\n"
    for log in logs:
        # log is a dict from database.py
        category_icon = {
            "expense": "💰",
            "task": "✅",
            "note": "📝",
            "reminder": "⏰"
        }.get(log["category"], "🔹")

        try:
            data = json.loads(log["structured_data"])
            summary = data.get("summary", log["raw_text"][:50])
        except:
            summary = log["raw_text"][:50]

        text += f"{category_icon} {summary}\n"

    await update.message.reply_text(text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    raw_stats = database.get_stats(update.effective_user.id)
    if not raw_stats:
        await update.message.reply_text(msgs["stats_empty"])
        return

    text = "📊 Статистика:\n\n"
    for cat, count in raw_stats:
        text += f"{cat.capitalize()}: {count}\n"

    await update.message.reply_text(text)

def main():
    database.init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
