import os
import re
import sqlite3
import json
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic
import speech_recognition as sr
from pydub import AudioSegment
import static_ffmpeg

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
        "Илтимос, тилни танланг / Iltimos, tilni tanlang / Пожалуйста, выберите язык:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang

    welcome_text = {
        "lang_uz_cyr": "✅ Тил танланди!\n\nОвозли ёки матнли хабар юборинг. Мен уларни тоифаларга ажратиб сақлайман.\n\nБуйруқлар:\n/history - Охирги 10 та қайд\n/summary - Умумий ҳисобот",
        "lang_uz_lat": "✅ Til tanlandi!\n\nOvozli yoki matnli xabar yuboring. Men ularni toifalarga ajratib saqlayman.\n\nBuyruqlar:\n/history - Oxirgi 10 ta qayd\n/summary - Umumiy hisobot",
        "lang_ru": "✅ Язык выбран!\n\nОтправьте голосовое или текстовое сообщение. Я категоризирую и сохраню его.\n\nКоманды:\n/history - Последние 10 записей\n/summary - Общий отчет"
    }

    await query.edit_message_text(welcome_text.get(lang, welcome_text["lang_uz_cyr"]))

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute("SELECT type, content, timestamp FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Ҳеч нарса топилмади." if lang == "lang_uz_cyr" else ("Hech narsa topilmadi." if lang == "lang_uz_lat" else "Ничего не найдено."))
        return

    res = "📜 Тарих / Tarix / История:\n\n"
    for rtype, content, ts in rows:
        res += f"🕒 {ts[:16]} | {rtype.upper()}\n📝 {content[:50]}...\n\n"

    await update.message.reply_text(res)

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute("SELECT type, content FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Маълумот етарли эмас." if lang == "lang_uz_cyr" else ("Ma'lumot yetarli emas." if lang == "lang_uz_lat" else "Недостаточно данных."))
        return

    wait_msg = await update.message.reply_text("📊 Ҳисобот тайёрланмоқда..." if lang == "lang_uz_cyr" else ("📊 Hisobot tayyorlanmoqda..." if lang == "lang_uz_lat" else "📊 Подготовка отчета..."))

    data_str = "\n".join([f"{t}: {c}" for t, c in rows])

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            system=f"Analyze these notes and provide a brief summary/analysis in {lang}.",
            messages=[{"role": "user", "content": data_str}]
        )
        await wait_msg.edit_text(message.content[0].text)
    except Exception as e:
        await wait_msg.edit_text(f"❌ Error: {str(e)}")

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    voice = update.message.voice

    wait_msg = await update.message.reply_text("🎤 Овоз ёзиб олиняпти..." if lang == "lang_uz_cyr" else ("🎤 Ovoz yozib olinyapti..." if lang == "lang_uz_lat" else "🎤 Голос записывается..."))

    file = await context.bot.get_file(voice.file_id)
    ogg_path = f"voice_{voice.file_id}.ogg"
    wav_path = f"voice_{voice.file_id}.wav"

    await file.download_to_drive(ogg_path)

    try:
        # Convert OGG to WAV
        audio = await asyncio.to_thread(AudioSegment.from_ogg, ogg_path)
        await asyncio.to_thread(audio.export, wav_path, format="wav")

        # Speech to Text
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = await asyncio.to_thread(recognizer.record, source)

            # Select language for STT
            stt_lang = "uz-UZ" if lang.startswith("lang_uz") else "ru-RU"
            text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=stt_lang)

        await wait_msg.edit_text(f"📝 Текст: {text}" if lang == "lang_uz_cyr" else (f"📝 Matn: {text}" if lang == "lang_uz_lat" else f"📝 Текст: {text}"))

        # Further processing
        await process_note_ai(update, context, text, wait_msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Хато: {str(e)}")
    finally:
        if os.path.exists(ogg_path): os.remove(ogg_path)
        if os.path.exists(wav_path): os.remove(wav_path)

async def process_note_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, wait_msg=None):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id

    system_prompt = """You are a smart trilingual personal assistant.
Analyze the user's input and categorize it.
Categories: 'expense' (харажат), 'task' (вазифа), 'idea' (ғоя), 'note' (эслатма).
Respond ONLY with a JSON object:
{"type": "category", "response": "Short summary or response in user's language"}
"""

    if not wait_msg:
        wait_msg = await update.message.reply_text("⌛...")

    await wait_msg.edit_text("🧠 Таҳлил қилиняпти..." if lang == "lang_uz_cyr" else ("🧠 Tahlil qilinyapti..." if lang == "lang_uz_lat" else "🧠 Анализирую..."))

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": text}]
        )

        raw_response = message.content[0].text
        # Robust JSON extraction
        match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            note_type = data.get("type", "note")
            ai_response = data.get("response", raw_response)
        else:
            note_type = "note"
            ai_response = raw_response

        # Save to DB
        conn = sqlite3.connect("notes.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO notes VALUES (?, ?, ?, ?)",
                       (user_id, note_type, text, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        type_labels = {
            "lang_uz_cyr": {"expense": "Харажат", "task": "Вазифа", "idea": "Ғоя", "note": "Эслатма"},
            "lang_uz_lat": {"expense": "Xarajat", "task": "Vazifa", "idea": "G'oya", "note": "Eslatma"},
            "lang_ru": {"expense": "Расход", "task": "Задача", "idea": "Идея", "note": "Заметка"}
        }

        label = type_labels.get(lang, type_labels["lang_uz_cyr"]).get(note_type, note_type)

        final_text = f"✅ Сақланди!\n\n📌 Тур: {label}\n🤖 {ai_response}" if lang == "lang_uz_cyr" else \
                     (f"✅ Saqlandi!\n\n📌 Tur: {label}\n🤖 {ai_response}" if lang == "lang_uz_lat" else \
                      f"✅ Сохранено!\n\n📌 Тип: {label}\n🤖 {ai_response}")

        await wait_msg.edit_text(final_text)

    except Exception as e:
        await wait_msg.edit_text(f"❌ Error: {str(e)}")

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    await process_note_ai(update, context, question)

def init_db():
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            user_id INTEGER,
            type TEXT,
            content TEXT,
            timestamp TEXT
        )
    """)
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
