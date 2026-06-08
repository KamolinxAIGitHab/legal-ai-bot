import os
import re
import sqlite3
import asyncio
import io
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

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "start": "✅ Тил танланди!\n\nОвозли хабар юборинг ёки матн кўринишида қайд ёзинг (харажат, вазифа ёки савол):",
        "wait": "⏳ Жавоб тайёрланмоқда...",
        "success": "✅ Сақланди!",
        "disclaimer": "\n\n⚠️ Жавоблар умумий ва таълимий мақсадда.",
        "error_api": "❌ CLAUDE_API_KEY топилмади.",
        "error_auth": "❌ API калит нотўғри.",
        "error_limit": "❌ API лимити тугади.",
        "error_gen": "❌ Хатолик юз берди.",
        "no_data": "📭 Маълумот топилмади.",
        "summary_prompt": "Қуйидаги қайдларни қисқача умумлаштириб беринг:",
    },
    "lang_uz_lat": {
        "start": "✅ Til tanlandi!\n\nOvozli xabar yuboring yoki matn ko'rinishida qayd yozing (xarajat, vazifa yoki savol):",
        "wait": "⏳ Javob tayyorlanmoqda...",
        "success": "✅ Saqlandi!",
        "disclaimer": "\n\n⚠️ Javoblar umumiy va ta'limiy maqsadda.",
        "error_api": "❌ CLAUDE_API_KEY topilmadi.",
        "error_auth": "❌ API kalit noto'g'ri.",
        "error_limit": "❌ API limiti tugadi.",
        "error_gen": "❌ Xatolik yuz berdi.",
        "no_data": "📭 Ma'lumot topilmadi.",
        "summary_prompt": "Quyidagi qaydlarni qisqacha umumlashtirib bering:",
    },
    "lang_ru": {
        "start": "✅ Язык выбран!\n\nОтправьте голосовое сообщение или напишите заметку (расход, задача или вопрос):",
        "wait": "⏳ Ответ готовится...",
        "success": "✅ Сохранено!",
        "disclaimer": "\n\n⚠️ Ответы носят общий и образовательный характер.",
        "error_api": "❌ CLAUDE_API_KEY не найден.",
        "error_auth": "❌ Неверный ключ API.",
        "error_limit": "❌ Лимит API исчерпан.",
        "error_gen": "❌ Произошла ошибка.",
        "no_data": "📭 Данные не найдены.",
        "summary_prompt": "Пожалуйста, кратко обобщите следующие записи:",
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
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    await query.edit_message_text(msgs["start"])

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def process_ai_request(text, lang, user_id):
    if lang == "lang_uz_cyr":
        system = """Сиз фойдали ёрдамчисиз. Фойдаланувчининг хабарини таҳлил қилинг ва уни қуйидаги тоифалардан бирига ажратинг:
- 'expense' (харажатлар)
- 'task' (вазифалар)
- 'legal' (қонунчилик/давлат харидлари бўйича саволлар)
- 'note' (оддий қайдлар)

Жавобни фақат JSON форматида қайтаринг:
{"type": "тоифа", "response": "сизнинг жавобингиз/хулосангиз"}

Қоидалар:
1. Фақат ўзбек тилида, кирилл алифбосида ёзинг.
2. 'legal' бўлса, Ўзбекистон қонунчилиги бўйича батафсил жавоб беринг.
3. 'expense' бўлса, харажатни тасдиқланг.
4. 'task' бўлса, вазифани қайд этганингизни айтинг."""
    elif lang == "lang_uz_lat":
        system = """Siz foydali yordamchisiz. Foydalanuvchining xabarini tahlil qiling va uni quyidagi toifalardan biriga ajrating:
- 'expense' (xarajatlar)
- 'task' (vazifalar)
- 'legal' (qonunchilik/davlat xaridlari bo'yicha savollar)
- 'note' (oddiy qaydlar)

Javobni faqat JSON formatida qaytaring:
{"type": "toifa", "response": "sizning javobingiz/xulosangiz"}

Qoidalar:
1. O'zbek tilida lotin alifbosida yozing.
2. 'legal' bo'lsa, O'zbekiston qonunchiligi bo'yicha batafsil javob bering.
3. 'expense' bo'lsa, xarajatni tasdiqlang.
4. 'task' bo'lsa, vazifani qayd etganingizni ayting."""
    else:
        system = """Вы полезный помощник. Проанализируйте сообщение пользователя и классифицируйте его:
- 'expense' (расходы)
- 'task' (задачи)
- 'legal' (вопросы по законодательству/госзакупкам)
- 'note' (простые заметки)

Верните ответ ТОЛЬКО в формате JSON:
{"type": "категория", "response": "ваш ответ/заключение"}

Правила:
1. Отвечайте на русском языке.
2. Если 'legal', дайте подробный ответ по законодательству Узбекистана.
3. Если 'expense', подтвердите расход.
4. Если 'task', подтвердите запись задачи."""

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": text}]
    )

    raw_response = message.content[0].text
    try:
        # Extract JSON if there's any surrounding text
        json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if json_match:
            import json
            result = json.loads(json_match.group())

            # Save to DB
            conn = sqlite3.connect('notes.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO notes (user_id, type, content) VALUES (?, ?, ?)',
                         (user_id, result.get('type', 'note'), text))
            conn.commit()
            conn.close()

            return result.get('response', raw_response)
    except Exception as e:
        print(f"AI Response parsing error: {e}")

    return clean_markdown(raw_response)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    text = update.message.text
    if not text:
        return

    wait_msg = await update.message.reply_text(msgs["wait"])

    try:
        if not CLAUDE_API_KEY:
            await wait_msg.edit_text(msgs["error_api"])
            return

        response = await process_ai_request(text, lang, update.effective_user.id)
        await wait_msg.edit_text(f"🤖 {response}{msgs['disclaimer']}")

    except anthropic.AuthenticationError:
        await wait_msg.edit_text(msgs["error_auth"])
    except anthropic.RateLimitError:
        await wait_msg.edit_text(msgs["error_limit"])
    except Exception as e:
        print(f"XATO: {e}")
        await wait_msg.edit_text(f"{msgs['error_gen']} {str(e)[:100]}")

async def process_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    ogg_bytes = await file.download_as_bytearray()

    # Convert OGG to WAV
    audio = await asyncio.to_thread(AudioSegment.from_ogg, io.BytesIO(ogg_bytes))
    wav_io = io.BytesIO()
    await asyncio.to_thread(audio.export, wav_io, format="wav")
    wav_io.seek(0)

    # Transcribe
    recognizer = sr.Recognizer()
    lang_code = "uz-UZ" # Default
    user_lang = context.user_data.get("lang", "lang_uz_cyr")
    if user_lang == "lang_ru":
        lang_code = "ru-RU"

    try:
        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)
            text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=lang_code)
            return text
    except sr.UnknownValueError:
        return None
    except Exception as e:
        print(f"Transcription error: {e}")
        return None

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    wait_msg = await update.message.reply_text(msgs["wait"])

    text = await process_voice(update, context)
    if not text:
        await wait_msg.edit_text(msgs["error_gen"])
        return

    try:
        response = await process_ai_request(text, lang, update.effective_user.id)
        await wait_msg.edit_text(f"🎤 {text}\n\n🤖 {response}{msgs['disclaimer']}")
    except Exception as e:
        print(f"XATO voice: {e}")
        await wait_msg.edit_text(f"{msgs['error_gen']} {str(e)[:100]}")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    user_id = update.effective_user.id

    conn = sqlite3.connect('notes.db')
    cursor = conn.cursor()
    cursor.execute('SELECT type, content, timestamp FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10', (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(msgs["no_data"])
        return

    history_text = "📜 History:\n" if lang == "lang_ru" else "📜 Тарих:\n"
    for row in rows:
        history_text += f"- [{row[2]}] {row[0]}: {row[1][:50]}...\n"

    await update.message.reply_text(history_text)

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    user_id = update.effective_user.id

    conn = sqlite3.connect('notes.db')
    cursor = conn.cursor()
    cursor.execute('SELECT content FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20', (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(msgs["no_data"])
        return

    wait_msg = await update.message.reply_text(msgs["wait"])
    notes_text = "\n".join([r[0] for r in rows])

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system="Summarize the notes provided by the user.",
            messages=[{"role": "user", "content": f"{msgs['summary_prompt']}\n\n{notes_text}"}]
        )
        summary = clean_markdown(message.content[0].text)
        await wait_msg.edit_text(f"📊 Summary:\n\n{summary}")
    except Exception as e:
        await wait_msg.edit_text(f"{msgs['error_gen']} {str(e)[:100]}")

def init_db():
    conn = sqlite3.connect('notes.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def main():
    static_ffmpeg.add_paths()
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
