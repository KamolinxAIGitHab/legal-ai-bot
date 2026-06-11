import sqlite3
import json
import asyncio
import speech_recognition as sr
import static_ffmpeg
static_ffmpeg.add_paths()
from pydub import AudioSegment

import os
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "wait": "⏳ Жавоб тайёрланмоқда...",
        "success": "✅ Бажарилди!",
        "disclaimer": "\n\n⚠️ Жавоблар умумий ва таълимий мақсадда.",
        "error_api": "❌ API калит топилмади.",
        "error_auth": "❌ API калит нотўғри.",
        "error_limit": "❌ API лимити тугади.",
        "error_gen": "❌ Хато юз берди.",
        "summary_prompt": "Қуйидаги қайдларни гуруҳларга ажратиб, қисқача хулоса беринг:",
        "no_data": "📭 Маълумот топилмади.",
        "start": "Ассалому алайкум! Тилни танланг / Assalomu alaykum! Tilni tanlang / Здравствуйте! Выберите язык:"
    },
    "lang_uz_lat": {
        "wait": "⏳ Javob tayyorlanmoqda...",
        "success": "✅ Bajarildi!",
        "disclaimer": "\n\n⚠️ Javoblar umumiy va ta'limiy maqsadda.",
        "error_api": "❌ API kalit topilmadi.",
        "error_auth": "❌ API kalit noto'g'ri.",
        "error_limit": "❌ API limiti tugadi.",
        "error_gen": "❌ Xato yuz berdi.",
        "summary_prompt": "Quyidagi qaydlarni guruhlarga ajratib, qisqacha xulosa bering:",
        "no_data": "📭 Ma'lumot topilmadi.",
        "start": "Assalomu alaykum! Tilni tanlang / Ассалому алайкум! Тилни танланг / Здравствуйте! Выберите язык:"
    },
    "lang_ru": {
        "wait": "⏳ Ответ готовится...",
        "success": "✅ Готово!",
        "disclaimer": "\n\n⚠️ Ответы носят общий и образовательный характер.",
        "error_api": "❌ API ключ не найден.",
        "error_auth": "❌ Неверный API ключ.",
        "error_limit": "❌ Лимит API исчерпан.",
        "error_gen": "❌ Произошла ошибка.",
        "summary_prompt": "Сгруппируйте следующие записи и дайте краткий обзор:",
        "no_data": "📭 Данные не найдены.",
        "start": "Здравствуйте! Выберите язык / Ассалому алайкум! Тилни танланг / Assalomu alaykum! Tilni tanlang:"
    }
}

def init_db():
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS notes
                 (user_id INTEGER, type TEXT, content TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(
        LOCALIZED_MESSAGES["lang_uz_cyr"]["start"],
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    msg = "✅ Тил танланди! Энди овозли хабар юборишингиз ёки савол ёзишингиз мумкин." if lang == "lang_uz_cyr" else \
          "✅ Til tanlandi! Endi ovozli xabar yuborishingiz yoki savol yozishingiz mumkin." if lang == "lang_uz_lat" else \
          "✅ Язык выбран! Теперь вы можете отправить голосовое сообщение или написать вопрос."
    await query.edit_message_text(msg)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    wait_msg = await update.message.reply_text(msgs["wait"])

    file = await context.bot.get_file(update.message.voice.file_id)
    ogg_path = f"voice_{update.message.voice.file_id}.ogg"
    wav_path = f"voice_{update.message.voice.file_id}.wav"

    try:
        await file.download_to_drive(ogg_path)

        # Convert OGG to WAV
        audio = await asyncio.to_thread(AudioSegment.from_ogg, ogg_path)
        await asyncio.to_thread(audio.export, wav_path, format="wav")

        # Transcribe
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = await asyncio.to_thread(recognizer.record, source)
            # Use appropriate language for STT
            stt_lang = "uz-UZ" if "uz" in lang else "ru-RU"
            text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=stt_lang)

        await handle_ai_logic(update, context, text, wait_msg)

    except Exception as e:
        print(f"VOICE ERROR: {e}")
        await wait_msg.edit_text(msgs["error_gen"])
    finally:
        if os.path.exists(ogg_path): os.remove(ogg_path)
        if os.path.exists(wav_path): os.remove(wav_path)

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def process_ai_request(text, lang):
    if not CLAUDE_API_KEY: return None
    system = f"""You are a personal assistant and legal expert for Uzbekistan.
Analyze input and return JSON with:
1. "type": "expense", "task", "legal", or "note".
2. "response": Helpful analysis in user's language ({lang}).
If expense/task, extract details. If legal (ZRU-684/ZRU-1005), provide advice. Return ONLY JSON."""
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    message = client.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=1024, system=system,
                                    messages=[{"role": "user", "content": text}])
    try:
        json_str = re.search(r'\{.*\}', message.content[0].text, re.DOTALL).group()
        return json.loads(json_str)
    except:
        return {"type": "note", "response": clean_markdown(message.content[0].text)}

async def handle_ai_logic(update, context, text, wait_msg):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    try:
        res = await process_ai_request(text, lang)
        if not res:
            await wait_msg.edit_text(msgs["error_api"])
            return
        if res["type"] in ["expense", "task", "note"]:
            from datetime import datetime
            conn = sqlite3.connect("notes.db")
            c = conn.cursor()
            c.execute("INSERT INTO notes VALUES (?, ?, ?, ?)", (update.effective_user.id, res["type"], text, datetime.now().isoformat()))
            conn.commit()
            conn.close()
        await wait_msg.edit_text(f"🤖 {res['response']}{msgs['disclaimer']}")
    except Exception as e:
        print(f"AI ERROR: {e}")
        await wait_msg.edit_text(msgs["error_gen"])

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    wait_msg = await update.message.reply_text(msgs["wait"])
    await handle_ai_logic(update, context, update.message.text, wait_msg)

async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    c.execute("SELECT type, content, timestamp FROM notes WHERE user_id=? ORDER BY timestamp DESC LIMIT 10", (update.effective_user.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text(msgs["no_data"])
        return
    res = "\n\n".join([f"📅 {r[2][:10]} | {r[0].upper()}\n{r[1]}" for r in rows])
    await update.message.reply_text(res)

async def handle_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    wait_msg = await update.message.reply_text(msgs["wait"])
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    c.execute("SELECT type, content FROM notes WHERE user_id=? ORDER BY timestamp DESC LIMIT 20", (update.effective_user.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await wait_msg.edit_text(msgs["no_data"])
        return
    data_str = "\n".join([f"- [{r[0]}] {r[1]}" for r in rows])
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        system=f"Analyze these notes and provide a concise summary in {lang}.",
        messages=[{"role": "user", "content": f"{msgs['summary_prompt']}\n\n{data_str}"}]
    )
    await wait_msg.edit_text(f"📊 {clean_markdown(message.content[0].text)}")

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", handle_history))
    app.add_handler(CommandHandler("summary", handle_summary))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
