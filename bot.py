import os
import re
import sqlite3
import asyncio
import io
import json
from datetime import datetime

import speech_recognition as sr
from pydub import AudioSegment
import static_ffmpeg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

static_ffmpeg.add_paths()

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "chosen": "✅ Тил танланди!\n\nОвозли ёки матнли хабар юборинг. Мен уни категорияларга ажратиб сақлаб қўяман.",
        "wait": "⏳ Ишланмоқда...",
        "success": "✅ Сақланди!\n\n📌 Тур: {type}\n📝 Мазмун: {response}",
        "error_api": "❌ API калит нотўғри.",
        "error_gen": "❌ Хатолик юз берди.",
        "transcribing": "🎤 Овоз матнга айлантирилмоқда...",
        "analyzing": "🧠 Таҳлил қилинмоқда...",
        "no_data": "📭 Маълумот топилмади.",
        "summary_prompt": "Сиз шахсий ёрдамчисиз. Қуйидаги охирги 50 та ёзувни таҳлил қилинг ва умумий хулоса беринг (харажатлар, вазифалар ва ҳ.к.):\n\n",
    },
    "lang_uz_lat": {
        "chosen": "✅ Til tanlandi!\n\nOvozli yoki matnli xabar yuboring. Men uni kategoriyalarga ajratib saqlab qo'yaman.",
        "wait": "⏳ Ishlanmoqda...",
        "success": "✅ Saqlandi!\n\n📌 Tur: {type}\n📝 Mazmun: {response}",
        "error_api": "❌ API kalit noto'g'ri.",
        "error_gen": "❌ Xatolik yuz berdi.",
        "transcribing": "🎤 Ovoz matnga aylantirilmoqda...",
        "analyzing": "🧠 Tahlil qilinmoqda...",
        "no_data": "📭 Ma'lumot topilmadi.",
        "summary_prompt": "Siz shaxsiy yordamchisiz. Quyidagi oxirgi 50 ta yozuvni tahlil qiling va umumiy xulosa bering (xarajatlar, vazifalar va h.k.):\n\n",
    },
    "lang_ru": {
        "chosen": "✅ Язык выбран!\n\nОтправьте голосовое или текстовое сообщение. Я категоризирую и сохраню его.",
        "wait": "⏳ Обработка...",
        "success": "✅ Сохранено!\n\n📌 Тип: {type}\n📝 Содержание: {response}",
        "error_api": "❌ Ошибка API ключа.",
        "error_gen": "❌ Произошла ошибка.",
        "transcribing": "🎤 Преобразование голоса в текст...",
        "analyzing": "🧠 Анализирую...",
        "no_data": "📭 Данных не найдено.",
        "summary_prompt": "Вы личный помощник. Проанализируйте последние 50 записей и дайте краткий обзор (расходы, задачи и т.д.):\n\n",
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
    lang = query.data
    context.user_data["lang"] = lang
    await query.edit_message_text(LOCALIZED_MESSAGES[lang]["chosen"])

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msg = await update.message.reply_text(LOCALIZED_MESSAGES[lang]["transcribing"])

    voice = update.message.voice
    voice_file = await context.bot.get_file(voice.file_id)

    ogg_path = f"voice_{voice.file_id}.ogg"
    wav_path = f"voice_{voice.file_id}.wav"

    await voice_file.download_to_drive(ogg_path)

    try:
        audio = await asyncio.to_thread(AudioSegment.from_ogg, ogg_path)
        await asyncio.to_thread(audio.export, wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)

        stt_lang = "uz-UZ" if "uz" in lang else "ru-RU"
        text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=stt_lang)

        await msg.edit_text(LOCALIZED_MESSAGES[lang]["analyzing"])
        await process_note_ai(update, context, text, msg)

    except Exception as e:
        print(f"Voice error: {e}")
        await msg.edit_text(LOCALIZED_MESSAGES[lang]["error_gen"])
    finally:
        if os.path.exists(ogg_path): os.remove(ogg_path)
        if os.path.exists(wav_path): os.remove(wav_path)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT type, content, timestamp FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 10",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(LOCALIZED_MESSAGES[lang]["no_data"])
        return

    history_text = "📜 *History (Last 10):*\n\n"
    for row in rows:
        history_text += f"🔹 [{row[0]}] {row[1]} ({row[2][:16]})\n"

    await update.message.reply_text(history_text, parse_mode="Markdown")

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id

    await update.message.reply_text(LOCALIZED_MESSAGES[lang]["analyzing"])

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT type, content FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 50",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(LOCALIZED_MESSAGES[lang]["no_data"])
        return

    context_text = "\n".join([f"- [{r[0]}] {r[1]}" for r in rows])

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=LOCALIZED_MESSAGES[lang]["summary_prompt"],
            messages=[{"role": "user", "content": context_text}]
        )
        await update.message.reply_text(f"📊 *Summary:*\n\n{message.content[0].text}", parse_mode="Markdown")
    except Exception as e:
        print(f"Summary error: {e}")
        await update.message.reply_text(LOCALIZED_MESSAGES[lang]["error_gen"])

async def process_note_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None, msg=None):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id

    if text is None:
        text = update.message.text

    system_prompt = """You are a personal assistant. Analyze the user's input (voice transcription or text) and categorize it.
Categories: 'expense' (харажат), 'task' (вазифа), 'note' (эслатма), 'legal' (қонунчилик/харид).
Return ONLY a JSON object:
{"type": "category_name", "response": "brief_summary_or_action"}

Language: Use the same language/script as the user (Uzbek Cyrillic, Uzbek Latin, or Russian).
"""

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": text}]
        )

        raw_response = message.content[0].text
        # Extract JSON if there's any surrounding text
        match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            data = {"type": "note", "response": raw_response}

        # Save to DB
        conn = sqlite3.connect("notes.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notes (user_id, type, content, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, data["type"], data["response"], datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

        success_msg = LOCALIZED_MESSAGES[lang]["success"].format(
            type=data["type"],
            response=data["response"]
        )

        if msg:
            await msg.edit_text(success_msg)
        else:
            await update.message.reply_text(success_msg)

    except Exception as e:
        print(f"AI error: {e}")
        error_msg = LOCALIZED_MESSAGES[lang]["error_gen"]
        if msg:
            await msg.edit_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

def init_db():
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_note_ai))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
