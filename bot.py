import os
import re
import json
import sqlite3
import asyncio
from datetime import datetime

import static_ffmpeg
from pydub import AudioSegment
import speech_recognition as sr
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

static_ffmpeg.add_paths()
TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

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
    await query.edit_message_text(
        "✅ Тил танланди!\n\nОвозли хабар юборинг ёки матн кўринишида ёзинг:"
    )

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "wait": "⏳ Жавоб тайёрланмоқда...",
        "transcribing": "🎤 Овоз таҳлил қилиняпти...",
        "analyzing": "🧠 Маълумот сараланяпти...",
        "success": "✅ Сақланди!",
        "error_gen": "❌ Хатолик юз берди.",
        "summary_prompt": "Қуйидаги қайдларни гуруҳларга бўлиб, қисқача хулоса беринг:"
    },
    "lang_uz_lat": {
        "wait": "⏳ Javob tayyorlanmoqda...",
        "transcribing": "🎤 Ovoz tahlil qilinyapti...",
        "analyzing": "🧠 Ma'lumot saralanyapti...",
        "success": "✅ Saqlandi!",
        "error_gen": "❌ Xatolik yuz berdi.",
        "summary_prompt": "Quyidagi qaydlarni guruhlarga bo'lib, qisqacha xulosa bering:"
    },
    "lang_ru": {
        "wait": "⏳ Ответ готовится...",
        "transcribing": "🎤 Голос анализируется...",
        "analyzing": "🧠 Данные обрабатываются...",
        "success": "✅ Сохранено!",
        "error_gen": "❌ Произошла ошибка.",
        "summary_prompt": "Сгруппируйте следующие записи и дайте краткий итог:"
    }
}

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    wait_msg = await update.message.reply_text(msgs["transcribing"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")

    ogg_file = f"voice_{update.message.message_id}.ogg"
    wav_file = f"voice_{update.message.message_id}.wav"

    try:
        voice = await update.message.voice.get_file()
        await voice.download_to_drive(ogg_file)

        # Convert OGG to WAV
        audio = await asyncio.to_thread(AudioSegment.from_file, ogg_file, format="ogg")
        await asyncio.to_thread(audio.export, wav_file, format="wav")

        # Transcribe
        recognizer = sr.Recognizer()
        stt_lang = "uz-UZ" if "uz" in lang else "ru-RU"
        with sr.AudioFile(wav_file) as source:
            audio_data = await asyncio.to_thread(recognizer.record, source)
            text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=stt_lang)

        await process_ai_request(update, context, text, lang, msgs, wait_msg)

    except Exception as e:
        await update.message.reply_text(f"{msgs['error_gen']} {str(e)}")
    finally:
        if os.path.exists(ogg_file): os.remove(ogg_file)
        if os.path.exists(wav_file): os.remove(wav_file)

async def process_note_ai(text, lang):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    system = """You are a helpful assistant. Analyze the user's note.
Categorize it as one of: expense, task, note, legal.
If it's an expense, extract the item and amount.
If it's a task, extract the action.
Return ONLY a JSON object: {"type": "...", "content": "..."}
Use the same language as the input for 'content'."""

    prompt = f"Analyze this note: {text}"

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        # Extract JSON from response
        match = re.search(r'\{.*\}', message.content[0].text, re.DOTALL)
        return json.loads(match.group())
    except:
        return {"type": "note", "content": text}

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    c.execute("SELECT type, content, timestamp FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (user_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        text = {
            "lang_uz_cyr": "📭 Рўйхат бўш.",
            "lang_uz_lat": "📭 Ro'yxat bo'sh.",
            "lang_ru": "📭 Список пуст."
        }.get(context.user_data.get("lang"), "📭 List is empty.")
        await update.message.reply_text(text)
        return

    title = {
        "lang_uz_cyr": "📜 Охирги 10 та қайд:\n\n",
        "lang_uz_lat": "📜 Oxirgi 10 ta qayd:\n\n",
        "lang_ru": "📜 Последние 10 записей:\n\n"
    }.get(context.user_data.get("lang"), "📜 Last 10 notes:\n\n")
    res = title
    for r in rows:
        ts = datetime.fromisoformat(r[2]).strftime("%Y-%m-%d %H:%M")
        res += f"🕒 {ts} | #{r[0]}\n📝 {r[1]}\n\n"

    await update.message.reply_text(res)

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    await update.message.reply_text(msgs["wait"])

    user_id = update.effective_user.id
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    c.execute("SELECT type, content FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50", (user_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        text = {
            "lang_uz_cyr": "📭 Маълумот етарли эмас.",
            "lang_uz_lat": "📭 Ma'lumot yetarli emas.",
            "lang_ru": "📭 Недостаточно данных."
        }.get(lang, "📭 Not enough data.")
        await update.message.reply_text(text)
        return

    data_str = "\n".join([f"- [{r[0]}] {r[1]}" for r in rows])

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        system=msgs["summary_prompt"],
        messages=[{"role": "user", "content": data_str}]
    )

    await update.message.reply_text(f"📊 Summary:\n\n{message.content[0].text}")

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    question = update.message.text
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    # Determine if it's a legal question or a personal note
    # If the question is long or contains "zru" or "qonun", treat as legal
    is_legal = len(question.split()) > 7 or any(kw in question.lower() for kw in ["zru", "qonun", "давлат", "харид"])

    if is_legal:
        await handle_legal_question(update, context, question, lang)
    else:
        await process_ai_request(update, context, question, lang, msgs)

async def process_ai_request(update, context, text, lang, msgs, wait_msg=None):
    if not wait_msg:
        wait_msg = await update.message.reply_text(msgs["analyzing"])

    try:
        ai_data = await process_note_ai(text, lang)

        conn = sqlite3.connect("notes.db")
        c = conn.cursor()
        c.execute("INSERT INTO notes (user_id, type, content, timestamp) VALUES (?, ?, ?, ?)",
                  (update.effective_user.id, ai_data["type"], ai_data["content"], datetime.now().isoformat()))
        conn.commit()
        conn.close()

        type_labels = {"lang_uz_cyr": "Тур", "lang_uz_lat": "Tur", "lang_ru": "Тип"}
        label = type_labels.get(lang, "Type")
        await wait_msg.edit_text(f"{msgs['success']}\n\n📝 {ai_data['content']}\n{label}: #{ai_data['type']}")
    except Exception as e:
        await wait_msg.edit_text(f"{msgs['error_gen']} {str(e)}")

async def handle_legal_question(update, context, question, lang):
    if lang == "lang_uz_cyr":
        system = "Сиз Ўзбекистон давлат харидлари ва қонунчилик бўйича мутахассиссиз. Кирилл алифбосида жавоб беринг."
    elif lang == "lang_uz_lat":
        system = "Siz O'zbekiston davlat xaridlari va qonunchilik bo'yicha mutaxasssissiz. Lotin alifbosida javob bering."
    else:
        system = "Вы эксперт по государственным закупкам и законодательству Узбекистана."

    wait_msg = await update.message.reply_text("⏳...")
    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)
        await wait_msg.edit_text(f"🤖 {answer}\n\n⚠️ Жавоблар умумий ва таълимий мақсадда.")
    except Exception as e:
        await wait_msg.edit_text(f"❌ {str(e)}")

def init_db():
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS notes
                 (user_id INTEGER, type TEXT, content TEXT, timestamp TEXT)""")
    conn.commit()
    conn.close()

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
