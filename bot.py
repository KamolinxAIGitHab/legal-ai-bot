import os
import re
import sqlite3
import json
import asyncio
import speech_recognition as sr
from pydub import AudioSegment
import static_ffmpeg

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

def init_db():
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

static_ffmpeg.add_paths()
init_db()

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "wait": "⏳ Жавоб тайёрланмоқда...",
        "error": "❌ Хатолик юз берди.",
        "success": "✅ Сақланди!",
        "unsupported": "❌ Кечирасиз, фақат матн ва овозли хабарларни қабул қиламан.",
        "no_data": "📭 Маълумотлар топилмади.",
        "history": "📊 Охирги 10 та қайднома:",
    },
    "lang_uz_lat": {
        "wait": "⏳ Javob tayyorlanmoqda...",
        "error": "❌ Xatolik yuz berdi.",
        "success": "✅ Saqlandi!",
        "unsupported": "❌ Kechirasiz, faqat matn va ovozli xabarlarni qabul qilaman.",
        "no_data": "📭 Ma'lumotlar topilmadi.",
        "history": "📊 Oxirgi 10 ta qaydnoma:",
    },
    "lang_ru": {
        "wait": "⏳ Подготовка ответа...",
        "error": "❌ Произошла ошибка.",
        "success": "✅ Сохранено!",
        "unsupported": "❌ Извините, я принимаю только текстовые и голосовые сообщения.",
        "no_data": "📭 Данные не найдены.",
        "history": "📊 Последние 10 записей:",
    }
}

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
    context.user_data["lang"] = query.data
    msg = {
        "lang_uz_cyr": "✅ Тил танланди!\n\nХаражатлар, вазифалар ёки қайдларни ёзинг ёки овозли хабар юборинг:",
        "lang_uz_lat": "✅ Til tanlandi!\n\nXarajatlar, vazifalar yoki qaydlarni yozing yoki ovozli xabar yuboring:",
        "lang_ru": "✅ Язык выбран!\n\nПишите расходы, задачи или заметки, либо отправьте голосовое сообщение:"
    }.get(query.data, "✅")
    await query.edit_message_text(msg)

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def process_ai_request(text, lang, user_id):
    if lang == "lang_uz_cyr":
        system = """Сиз фойдали ёрдамчисиз. Фойдаланувчининг хабарини таҳлил қилинг ва JSON форматда жавоб беринг:
{
  "type": "expense" | "task" | "legal" | "note",
  "response": "фойдаланувчига қисқа ва фойдали жавоб"
}
Қоидалар:
1. 'expense' - харажатлар учун
2. 'task' - вазифалар ва режалар учун
3. 'legal' - қонунчиликка оид саволлар учун
4. 'note' - бошқа барча қайдлар учун
Фақат JSON қайтаринг."""
    elif lang == "lang_uz_lat":
        system = """Siz foydali yordamchisiz. Foydalanuvchining xabarini tahlil qiling va JSON formatda javob bering:
{
  "type": "expense" | "task" | "legal" | "note",
  "response": "foydalanuvchiga qisqa va foydali javob"
}
Faqat JSON qaytaring."""
    else:
        system = """Вы полезный помощник. Проанализируйте сообщение пользователя и ответьте в формате JSON:
{
  "type": "expense" | "task" | "legal" | "note",
  "response": "краткий и полезный ответ пользователю"
}
Возвращайте только JSON."""

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": text}]
    )

    raw_text = message.content[0].text
    # Robust JSON parsing
    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group(0))
    else:
        # Fallback if AI didn't follow JSON format
        result = {"type": "note", "response": clean_markdown(raw_text)}

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO notes (user_id, type, content) VALUES (?, ?, ?)",
        (user_id, result["type"], text)
    )
    conn.commit()
    conn.close()

    return result["response"]

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    wait_msg = await update.message.reply_text(msgs["wait"])

    voice = await update.message.voice.get_file()
    ogg_path = f"voice_{update.message.message_id}.ogg"
    wav_path = f"voice_{update.message.message_id}.wav"

    try:
        await voice.download_to_drive(ogg_path)

        audio = await asyncio.to_thread(AudioSegment.from_ogg, ogg_path)
        await asyncio.to_thread(audio.export, wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = await asyncio.to_thread(recognizer.record, source)

        stt_lang = "uz-UZ" if "uz" in lang else "ru-RU"
        text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=stt_lang)

        response = await process_ai_request(text, lang, update.effective_user.id)
        await wait_msg.edit_text(f"🎤 {text}\n\n🤖 {response}")

    except Exception as e:
        print(f"VOICE ERROR: {e}")
        await wait_msg.edit_text(msgs["error"])
    finally:
        for p in [ogg_path, wav_path]:
            if os.path.exists(p):
                os.remove(p)

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    question = update.message.text

    wait_msg = await update.message.reply_text(msgs["wait"])

    try:
        if not CLAUDE_API_KEY:
            await wait_msg.edit_text("❌ CLAUDE_API_KEY not found.")
            return

        response = await process_ai_request(question, lang, update.effective_user.id)
        await wait_msg.edit_text(f"🤖 {response}")

    except Exception as e:
        print(f"ERROR: {e}")
        await wait_msg.edit_text(msgs["error"])

async def handle_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    await update.message.reply_text(msgs["unsupported"])

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    user_id = update.effective_user.id

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT type, content, timestamp FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(msgs["no_data"])
        return

    text = f"{msgs['history']}\n\n"
    for row in rows:
        emoji = {"expense": "💸", "task": "✅", "legal": "⚖️", "note": "📝"}.get(row[0], "📌")
        text += f"{emoji} {row[1]} ({row[2]})\n"

    await update.message.reply_text(text)

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    user_id = update.effective_user.id

    wait_msg = await update.message.reply_text(msgs["wait"])

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT type, content, timestamp FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 30",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await wait_msg.edit_text(msgs["no_data"])
        return

    data_str = "\n".join([f"Type: {r[0]}, Content: {r[1]}, Time: {r[2]}" for r in rows])

    if lang == "lang_uz_cyr":
        system = "Сиз таҳлилчисиз. Фойдаланувчининг охирги қайдларини таҳлил қилинг ва хулоса беринг (харажатлар суммаси, муҳим вазифалар ва ҳ.к.). Фақат кириллда ёзинг."
    elif lang == "lang_uz_lat":
        system = "Siz tahlilchisiz. Foydalanuvchining oxirgi qaydlarini tahlil qiling va xulosa bering (xarajatlar summasi, muhim vazifalar va h.k.)."
    else:
        system = "Вы аналитик. Проанализируйте последние записи пользователя и дайте краткий отчет (сумма расходов, важные задачи и т.д.)."

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": f"Data to analyze:\n{data_str}"}]
    )

    analysis = clean_markdown(message.content[0].text)
    await wait_msg.edit_text(f"📊 {analysis}")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.TEXT & ~filters.VOICE, handle_unsupported))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
