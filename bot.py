import os
import re
import json
import asyncio
import sqlite3
import static_ffmpeg

static_ffmpeg.add_paths()

from pydub import AudioSegment
import speech_recognition as sr
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

def init_db():
    conn = sqlite3.connect('notes.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS notes
                 (user_id INTEGER, type TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "wait": "⏳ Кутинг...",
        "transcribing": "🎙 Овоз матнга айлантирилмоқда...",
        "analyzing": "🧠 Таҳлил қилинмоқда...",
        "error": "❌ Хатолик юз берди:",
        "footer": "Жавоблар умумий ва таълимий мақсадда.",
        "start_msg": "✅ Тил танланди!\n\nСавол ёзинг ёки овозли хабар юборинг (харажатлар, вазифалар ёки ҳуқуқий саволлар):"
    },
    "lang_uz_lat": {
        "wait": "⏳ Kuting...",
        "transcribing": "🎙 Ovoz matnga aylantirilmoqda...",
        "analyzing": "🧠 Tahlil qilinmoqda...",
        "error": "❌ Xatolik yuz berdi:",
        "footer": "Javoblar umumiy va ta'limiy maqsadda.",
        "start_msg": "✅ Til tanlandi!\n\nSavol yozing yoki ovozli xabar yuboring (xarajatlar, vazifalar yoki huquqiy savollar):"
    },
    "lang_ru": {
        "wait": "⏳ Подождите...",
        "transcribing": "🎙 Голос преобразуется в текст...",
        "analyzing": "🧠 Анализируется...",
        "error": "❌ Произошла ошибка:",
        "footer": "Ответы носят общий и образовательный характер.",
        "start_msg": "✅ Язык выбран!\n\nНапишите вопрос или отправьте голосовое сообщение (расходы, задачи или юридические вопросы):"
    }
}

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
    await query.edit_message_text(LOCALIZED_MESSAGES[lang]["start_msg"])

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    wait_msg = await update.message.reply_text(msgs["wait"])

    ogg_path, wav_path = "", ""
    try:
        voice = await update.message.voice.get_file()
        ogg_path, wav_path = f"{voice.file_id}.ogg", f"{voice.file_id}.wav"
        await voice.download_to_drive(ogg_path)

        await wait_msg.edit_text(msgs["transcribing"])
        audio = await asyncio.to_thread(AudioSegment.from_file, ogg_path)
        await asyncio.to_thread(audio.export, wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = await asyncio.to_thread(recognizer.record, source)
            stt_lang = "uz-UZ" if "uz" in lang else "ru-RU"
            text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=stt_lang)

        await wait_msg.edit_text(msgs["analyzing"])
        await process_ai_request(update, context, text, wait_msg)

    except Exception as e:
        await wait_msg.edit_text(f"{msgs['error']} {str(e)[:100]}")
    finally:
        for p in [ogg_path, wav_path]:
            if p and os.path.exists(p): os.remove(p)

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    wait_msg = await update.message.reply_text(msgs["wait"])
    await process_ai_request(update, context, update.message.text, wait_msg)

async def process_ai_request(update, context, question, wait_msg):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    if lang == "lang_uz_cyr":
        system = """Сиз юридик мутахассис ва шахсий ёрдамчисиз.
Жавобни фақат JSON форматида қайтаринг:
{"type": "expense/task/legal", "response": "матн"}
1. Агар харажат бўлса: type=expense
2. Агар вазифа бўлса: type=task
3. Агар юридик бўлса: type=legal
Қоидалар: фақат кириллда, Markdown-сиз."""
    elif lang == "lang_uz_lat":
        system = """Siz yuridik mutaxassis va shaxsiy yordamchisiz.
Javobni faqat JSON formatida qaytaring:
{"type": "expense/task/legal", "response": "matn"}
Qoidalar: faqat lotin, Markdown-siz."""
    else:
        system = """Вы юридический эксперт и личный помощник.
Верните ответ только в формате JSON:
{"type": "expense/task/legal", "response": "текст"}
Правила: без Markdown."""

    try:
        if not CLAUDE_API_KEY:
            await wait_msg.edit_text("❌ CLAUDE_API_KEY not found.")
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        raw_res = message.content[0].text
        try:
            data = json.loads(raw_res)
            msg_type = data.get("type", "legal")
            final_resp = data.get("response", raw_res)

            conn = sqlite3.connect('notes.db')
            c = conn.cursor()
            c.execute("INSERT INTO notes (user_id, type, content) VALUES (?, ?, ?)",
                      (update.effective_user.id, msg_type, question))
            conn.commit()
            conn.close()

            await wait_msg.edit_text(f"🤖 {final_resp}\n\n⚠️ {LOCALIZED_MESSAGES[lang]['footer']}")
        except:
            await wait_msg.edit_text(f"🤖 {raw_res}\n\n⚠️ {LOCALIZED_MESSAGES[lang]['footer']}")

    except Exception as e:
        await wait_msg.edit_text(f"❌ Error: {type(e).__name__}")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
