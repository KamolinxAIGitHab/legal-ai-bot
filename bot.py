import os
import re
import sqlite3
import speech_recognition as sr
from pydub import AudioSegment
import static_ffmpeg
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

static_ffmpeg.add_paths()

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

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "chosen": "✅ Тил танланди!\n\nДавлат харидлари, қайдлар ёки харажатларингизни овозли ёки матнли кўринишда юборинг:",
        "wait": "⏳ Таҳлил қилинмоқда...",
        "voice_wait": "⏳ Овоз таҳлил қилинмоқда...",
        "history_empty": "📭 Сизда ҳали қайдлар йўқ.",
        "history_head": "📜 Охирги қайдларингиз:\n\n",
        "summary_empty": "📭 Анализ қилиш учун маълумот етарли эмас.",
        "summary_wait": "📊 Маълумотлар таҳлил қилинмоқда...",
        "summary_head": "📊 Анализ натижаси:\n\n",
        "error_voice": "❌ Овозни танишда хатолик: ",
        "error_gen": "❌ Хатолик юз берди: "
    },
    "lang_uz_lat": {
        "chosen": "✅ Til tanlandi!\n\nDavlat xaridlari, qaydlar yoki xarajatlaringizni ovozli yoki matnli ko'rinishda yuboring:",
        "wait": "⏳ Tahlil qilinmoqda...",
        "voice_wait": "⏳ Ovoz tahlil qilinmoqda...",
        "history_empty": "📭 Sizda hali qaydlar yo'q.",
        "history_head": "📜 Oxirgi qaydlaringiz:\n\n",
        "summary_empty": "📭 Analiz qilish uchun ma'lumot yetarli emas.",
        "summary_wait": "📊 Ma'lumotlar tahlil qilinmoqda...",
        "summary_head": "📊 Analiz natijasi:\n\n",
        "error_voice": "❌ Ovozni tanishda xatolik: ",
        "error_gen": "❌ Xatolik yuz berdi: "
    },
    "lang_ru": {
        "chosen": "✅ Язык выбран!\n\nОтправляйте голосовые или текстовые заметки, расходы или вопросы по госзакупкам:",
        "wait": "⏳ Анализируется...",
        "voice_wait": "⏳ Голос анализируется...",
        "history_empty": "📭 У вас пока нет заметок.",
        "history_head": "📜 Ваши последние заметки:\n\n",
        "summary_empty": "📭 Недостаточно данных для анализа.",
        "summary_wait": "📊 Данные анализируются...",
        "summary_head": "📊 Результат анализа:\n\n",
        "error_voice": "❌ Ошибка при распознавании голоса: ",
        "error_gen": "❌ Произошла ошибка: "
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

    await update.message.reply_chat_action("record_voice")
    wait_msg = await update.message.reply_text(LOCALIZED_MESSAGES[lang]["voice_wait"])

    file = await context.bot.get_file(voice.file_id)
    ogg_path = f"voice_{voice.file_id}.ogg"
    wav_path = f"voice_{voice.file_id}.wav"

    await file.download_to_drive(ogg_path)

    try:
        audio = AudioSegment.from_ogg(ogg_path)
        audio.export(wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            # Use 'uz-UZ' for both Latin and Cyrillic Uzbek, 'ru-RU' for Russian
            stt_lang = "ru-RU" if lang == "lang_ru" else "uz-UZ"
            text = recognizer.recognize_google(audio_data, language=stt_lang)

            # Forward text to AI processing
            await process_note_ai(update, context, text, wait_msg)

    except Exception as e:
        await wait_msg.edit_text(f"{LOCALIZED_MESSAGES[lang]['error_voice']}{str(e)}")
    finally:
        if os.path.exists(ogg_path): os.remove(ogg_path)
        if os.path.exists(wav_path): os.remove(wav_path)

async def process_note_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, wait_msg=None):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    if not wait_msg:
        await update.message.reply_chat_action("typing")
        wait_msg = await update.message.reply_text(LOCALIZED_MESSAGES[lang]["wait"])

    system = """Сиз фойдаланувчининг овозли ёки матнли қайдларини таҳлил қилувчи ёрдамчисиз.
Кирувчи хабарни қуйидаги тоифалардан бирига ажратинг: 'expense' (харажат), 'task' (вазифа), 'legal' (ҳуқуқий савол), 'note' (оддий қайд).

Жавобни ҚАТЪИЙ JSON форматида қайтаринг:
{
  "type": "expense" | "task" | "legal" | "note",
  "response": "Фойдаланувчи учун қисқа ва фойдали жавоб ёки тасдиқ"
}

Қоидалар:
1. Агар 'legal' бўлса, Ўзбекистон қонунчилиги бўйича батафсил жавоб беринг.
2. Тилни фойдаланувчи тилига мосланг (кирилл, лотин ёки рус).
3. Markdown ишлатманг."""

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": text}]
        )

        raw_res = message.content[0].text
        import json
        match = re.search(r'\{.*\}', raw_res, re.DOTALL)
        if not match:
            raise ValueError("AI response did not contain JSON")

        res_data = json.loads(match.group())
        note_type = res_data.get("type", "note")
        answer = res_data.get("response", "")

        if note_type != "legal":
            conn = sqlite3.connect("notes.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO notes VALUES (?, ?, ?, ?)",
                         (update.effective_user.id, note_type, text, datetime.now().isoformat()))
            conn.commit()
            conn.close()

        await wait_msg.edit_text(f"🤖 {answer}")

    except Exception as e:
        await wait_msg.edit_text(f"{LOCALIZED_MESSAGES[lang]['error_gen']}{str(e)}")

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_note_ai(update, context, update.message.text)

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute("SELECT type, content, timestamp FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(LOCALIZED_MESSAGES[lang]["history_empty"])
        return

    history_text = LOCALIZED_MESSAGES[lang]["history_head"]
    type_icons = {"expense": "💰", "task": "✅", "note": "📝"}
    for r_type, content, ts in rows:
        icon = type_icons.get(r_type, "🔹")
        dt = datetime.fromisoformat(ts).strftime("%d.%m %H:%M")
        history_text += f"{icon} [{dt}] {content[:100]}\n"

    await update.message.reply_text(history_text)

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute("SELECT content FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(LOCALIZED_MESSAGES[lang]["summary_empty"])
        return

    await update.message.reply_chat_action("typing")
    wait_msg = await update.message.reply_text(LOCALIZED_MESSAGES[lang]["summary_wait"])

    notes_text = "\n".join([r[0] for r in rows])
    system = "Сиз фойдаланувчининг охирги қайдлари асосида қисқача хулоса ва тавсиялар берувчи ёрдамчисиз. Харажатлар, вазифалар ва муҳим нуқталарни белгиланг."

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": f"Қуйидаги қайдларни анализ қилиб, хулоса бер:\n\n{notes_text}"}]
        )
        await wait_msg.edit_text(f"{LOCALIZED_MESSAGES[lang]['summary_head']}{message.content[0].text}")
    except Exception as e:
        await wait_msg.edit_text(f"{LOCALIZED_MESSAGES[lang]['error_gen']}{str(e)}")

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("summary", show_summary))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
