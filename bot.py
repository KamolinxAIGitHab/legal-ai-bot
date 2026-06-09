import json
import speech_recognition as sr
from pydub import AudioSegment
import static_ffmpeg
import sqlite3
import asyncio
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
        "wait": "⏳ Илтимос, кутинг...",
        "transcribing": "🎙 Овоз матнга айлантирилмоқда...",
        "processing": "🤖 Сунъий интеллект таҳлил қилмоқда...",
        "success": "✅ Сақланди!",
        "error_api": "❌ API калит топилмади.",
        "error_auth": "❌ API калит нотўғри.",
        "error_limit": "❌ API лимити тугади.",
        "error_gen": "❌ Хатолик юз берди.",
        "unsupported": "⚠️ Фақат матнли ва овозли хабарлар қабул қилинади.",
        "no_data": "📭 Сизда ҳали сақланган маълумотлар йўқ.",
        "summary_prompt": "Қуйидаги маълумотларни таҳлил қилиб, қисқача хулоса беринг:",
    },
    "lang_uz_lat": {
        "wait": "⏳ Iltimos, kuting...",
        "transcribing": "🎙 Ovoz matnga aylantirilmoqda...",
        "processing": "🤖 Sun'iy intellekt tahlil qilmoqda...",
        "success": "✅ Saqlandi!",
        "error_api": "❌ API kalit topilmadi.",
        "error_auth": "❌ API kalit noto'g'ri.",
        "error_limit": "❌ API limiti tugadi.",
        "error_gen": "❌ Xatolik yuz berdi.",
        "unsupported": "⚠️ Faqat matnli va ovozli xabarlar qabul qilinadi.",
        "no_data": "📭 Sizda hali saqlangan ma'lumotlar yo'q.",
        "summary_prompt": "Quyidagi ma'lumotlarni tahlil qilib, qisqacha xulosa bering:",
    },
    "lang_ru": {
        "wait": "⏳ Пожалуйста, подождите...",
        "transcribing": "🎙 Голос преобразуется в текст...",
        "processing": "🤖 ИИ анализирует данные...",
        "success": "✅ Сохранено!",
        "error_api": "❌ API ключ не найден.",
        "error_auth": "❌ Неверный API ключ.",
        "error_limit": "❌ Лимит API исчерпан.",
        "error_gen": "❌ Произошла ошибка.",
        "unsupported": "⚠️ Принимаются только текстовые и голосовые сообщения.",
        "no_data": "📭 У вас еще нет сохраненных данных.",
        "summary_prompt": "Проанализируйте следующие данные и дайте краткое резюме:",
    }
}

static_ffmpeg.add_paths()

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

def save_note(user_id, note_type, content):
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO notes (user_id, type, content) VALUES (?, ?, ?)",
        (user_id, note_type, content)
    )
    conn.commit()
    conn.close()

async def transcribe_voice(file_path, language_code):
    recognizer = sr.Recognizer()
    try:
        # Convert OGG to WAV
        audio = await asyncio.to_thread(AudioSegment.from_file, file_path, format="ogg")
        wav_path = file_path.replace(".ogg", ".wav")
        await asyncio.to_thread(audio.export, wav_path, format="wav")

        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=language_code)
            return text
    except Exception as e:
        print(f"Transcription error: {e}")
        return None
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        wav_path = file_path.replace(".ogg", ".wav")
        if os.path.exists(wav_path):
            os.remove(wav_path)

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
    msg = (
        "✅ Тил танланди!\n\n"
        "Энди сиз овозли ёки матнли хабар юборишингиз мумкин. "
        "Мен уларни сақлаб қўяман ва таҳлил қиламан."
    ) if query.data == "lang_uz_cyr" else (
        "✅ Til tanlandi!\n\n"
        "Endi siz ovozli yoki matnli xabar yuborishingiz mumkin. "
        "Men ularni saqlab qo'yaman va tahlil qilaman."
    ) if query.data == "lang_uz_lat" else (
        "✅ Язык выбран!\n\n"
        "Теперь вы можете отправлять голосовые или текстовые сообщения. "
        "Я сохраню их и проанализирую."
    )
    await query.edit_message_text(msg)

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def process_ai_request(text, lang):
    if lang == "lang_uz_cyr":
        system = """Сиз шахсий ёрдамчисиз. Фойдаланувчи юборган хабарни таҳлил қилинг ва қуйидаги форматда JSON қайтаринг:
{
  "type": "expense" (харажат), "task" (вазифа), "legal" (қонуний), ёки "note" (қайд),
  "response": "фойдаланувчига қисқа ва аниқ жавоб (масалан: '100 000 сўм харажат сақланди')"
}
Фақат JSON қайтаринг."""
    elif lang == "lang_uz_lat":
        system = """Siz shaxsiy yordamchisiz. Foydalanuvchi yuborgan xabarni tahlil qiling va quyidagi formatda JSON qaytaring:
{
  "type": "expense" (xarajat), "task" (vazifa), "legal" (qonuniy), yoki "note" (qayd),
  "response": "foydalanuvchiga qisqa va aniq javob (masalan: '100 000 so'm xarajat saqlandi')"
}
Faqat JSON qaytaring."""
    else:
        system = """Вы личный помощник. Проанализируйте сообщение пользователя и верните JSON в следующем формате:
{
  "type": "expense" (расход), "task" (задача), "legal" (юридический), или "note" (заметка),
  "response": "краткий и четкий ответ пользователю (например: 'Расход 100 000 сум сохранен')"
}
Возвращайте только JSON."""

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": text}]
        )
        raw_response = message.content[0].text
        # Extract JSON from response in case there is some extra text
        match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"type": "note", "response": raw_response}
    except Exception as e:
        print(f"AI error: {e}")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang)

    if update.message.voice:
        status_msg = await update.message.reply_text(msgs["transcribing"])
        file = await context.bot.get_file(update.message.voice.file_id)
        file_path = f"voice_{update.message.voice.file_id}.ogg"
        await file.download_to_drive(file_path)

        stt_lang = "uz-UZ" if lang.startswith("lang_uz") else "ru-RU"
        text = await transcribe_voice(file_path, stt_lang)
        if not text:
            await status_msg.edit_text(msgs["error_gen"])
            return
        await status_msg.edit_text(f"📝: {text}\n\n{msgs['processing']}")
    else:
        text = update.message.text
        status_msg = await update.message.reply_text(msgs["processing"])

    ai_res = await process_ai_request(text, lang)
    if ai_res:
        save_note(update.effective_user.id, ai_res["type"], text)
        await status_msg.edit_text(f"🤖 {ai_res['response']}")
    else:
        await status_msg.edit_text(msgs["error_gen"])

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang)
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

    history_text = "📖 *History:*\n\n" if lang == "lang_ru" else "📖 *Тарих:*\n\n"
    for row in rows:
        history_text += f"🔹 [{row[0].upper()}] {row[1]}\n_{row[2]}_\n\n"

    await update.message.reply_text(history_text, parse_mode="Markdown")

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang)
    user_id = update.effective_user.id

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute("SELECT type, content FROM notes WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(msgs["no_data"])
        return

    wait_msg = await update.message.reply_text(msgs["wait"])

    data_str = "\n".join([f"- {r[0]}: {r[1]}" for r in rows])
    prompt = f"{msgs['summary_prompt']}\n\n{data_str}"

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system="You are a helpful assistant providing a summary of user notes.",
            messages=[{"role": "user", "content": prompt}]
        )
        summary = clean_markdown(message.content[0].text)
        await wait_msg.edit_text(f"📊 *Summary:*\n\n{summary}", parse_mode="Markdown")
    except Exception as e:
        print(f"Summary error: {e}")
        await wait_msg.edit_text(msgs["error_gen"])

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("summary", show_summary))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler((filters.TEXT | filters.VOICE) & ~filters.COMMAND, handle_message))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
