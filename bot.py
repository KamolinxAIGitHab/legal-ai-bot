import os
import re
import sqlite3
import asyncio
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
        "welcome": "✅ Тил танланди!\n\nЭнди сиз овозли ёки матнли хабар юборишингиз мумкин.\n\nМен:\n1. Харажатларингизни ҳисоблайман\n2. Вазифаларингизни эслаб қоламан\n3. Давлат харидлари бўйича саволларга жавоб бераман\n\nБуйруқлар:\n/history - охирги ёзувлар\n/summary - ҳафталик таҳлил",
        "wait_voice": "⏳ Овозли хабар юкланмоқда...",
        "wait_ai": "⏳ Таҳлил қилинмоқда...",
        "history_empty": "📭 Ҳозирча маълумотлар йўқ.",
        "history_title": "📜 Охирги 10 та ёзув:\n\n",
        "summary_wait": "📊 Маълумотлар таҳлил қилинмоқда...",
        "summary_title": "📝 Хулоса:",
        "error_voice": "❌ Овозни қайта ишлашда хато:",
        "stt_prefix": "🎤 Транскрипция:"
    },
    "lang_uz_lat": {
        "welcome": "✅ Til tanlandi!\n\nEndi siz ovozli yoki matnli xabar yuborishingiz mumkin.\n\nMen:\n1. Xarajatlaringizni hisoblayman\n2. Vazifalaringizni eslab qolaman\n3. Davlat xaridlari bo'yicha savollarga javob beraman\n\nBuyruqlar:\n/history - oxirgi yozuvlar\n/summary - haftalik tahlil",
        "wait_voice": "⏳ Ovozli xabar yuklanmoqda...",
        "wait_ai": "⏳ Tahlil qilinmoqda...",
        "history_empty": "📭 Hozircha ma'lumotlar yo'q.",
        "history_title": "📜 Oxirgi 10 ta yozuv:\n\n",
        "summary_wait": "📊 Ma'lumotlar tahlil qilinmoqda...",
        "summary_title": "📝 Xulosa:",
        "error_voice": "❌ Ovozni qayta ishlashda xato:",
        "stt_prefix": "🎤 Transkripsiya:"
    },
    "lang_ru": {
        "welcome": "✅ Язык выбран!\n\nТеперь вы можете отправлять голосовые или текстовые сообщения.\n\nЯ могу:\n1. Считать ваши расходы\n2. Запоминать задачи\n3. Отвечать на вопросы по госзакупкам\n\nКоманды:\n/history - последние записи\n/summary - недельный анализ",
        "wait_voice": "⏳ Загрузка голосового сообщения...",
        "wait_ai": "⏳ Анализ данных...",
        "history_empty": "📭 Пока данных нет.",
        "history_title": "📜 Последние 10 записей:\n\n",
        "summary_wait": "📊 Анализирую данные...",
        "summary_title": "📝 Итог:",
        "error_voice": "❌ Ошибка при обработке голоса:",
        "stt_prefix": "🎤 Транскрипция:"
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
    msg = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    await query.edit_message_text(msg["welcome"])

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    question = update.message.text

    # Check if it's a "note" type request or legal question
    # For simplicity, if it's short or contains keywords, treat as note/expense/task
    # Otherwise, treat as legal question.
    # Or even better: let Claude decide in process_ai_request first,
    # but handle_question was originally for legal.
    # Let's keep legal functionality but also allow notes.

    # If question is explicitly a legal question (long and formal), handle as such.
    # Otherwise, prioritize personal note/assistant functionality.
    is_legal_question = len(question.split()) > 10 and any(k in question.lower() for k in ["қонун", "харид", "молия", "tender", "xarid", "qonun"])

    if not is_legal_question:
        await process_ai_request(update, context, question)
        return

    if lang == "lang_uz_cyr":
        system = """Сиз Ўзбекистон давлат харидлари ва қонунчилик бўйича мутахассиссиз.
Қатъий қоидалар:
1. Фақат ўзбек тилида, кирилл алифбосида ёзинг
2. Лотин ҳарфларини ИШЛАТМАНГ
3. Грамматик хатоларсиз ёзинг
4. Барча сўзлар тўғри кирилл алифбосида бўлсин
5. Рақамли рўйхат билан аниқ жавоб беринг
6. Markdown белгиларини ИШЛАТМАНГ
7. Оддий текст форматида ёзинг
8. Номаълум бўлса — расмий манбага мурожаат қилинг денг"""

    elif lang == "lang_uz_lat":
        system = """Siz O'zbekiston davlat xaridlari va qonunchilik bo'yicha mutaxasssissiz.
Qoidalar:
1. O'zbek tilida lotin alifbosida javob bering
2. Markdown belgilarini ISHLATMANG
3. Oddiy tekst formatida yozing
4. Noma'lum bo'lsa — rasmiy manbaga murojaat qiling deng"""

    else:
        system = """Вы эксперт по государственным закупкам и законодательству Узбекистана.
Правила:
1. Отвечайте на русском языке
2. НЕ используйте Markdown
3. Пишите обычным текстом
4. Если не уверены — напишите: Обратитесь к официальному источнику"""

    await update.message.reply_text("⏳ Жавоб тайёрланмоқда...")

    try:
        if not CLAUDE_API_KEY:
            await update.message.reply_text(
                "❌ CLAUDE_API_KEY топилмади. Railway Variables ни текширинг."
            )
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)
        await update.message.reply_text(
            f"🤖 {answer}\n\n⚠️ Жавоблар умумий ва таълимий мақсадда."
        )

    except anthropic.AuthenticationError:
        await update.message.reply_text(
            "❌ API калит нотўғри. CLAUDE_API_KEY ни текширинг."
        )
    except anthropic.RateLimitError:
        await update.message.reply_text(
            "❌ API лимити тугади. Кейинроқ уриниб кўринг."
        )
    except Exception as e:
        print(f"XATO TURI: {type(e).__name__}")
        print(f"XATO MATNI: {e}")
        await update.message.reply_text(
            f"❌ Хато: {type(e).__name__}: {str(e)[:200]}"
        )

import json

async def process_ai_request(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, wait_msg=None):
    lang = context.user_data.get("lang", "lang_uz_cyr")

    system_prompt = """Сиз фойдали ёрдамчисиз. Фойдаланувчининг матнини (ёки овозли хабаридан олинган транскрипцияни) таҳлил қилинг.
Агар бу харажат бўлса, уни 'expense' турига ажратинг.
Агар бу қилиниши керак бўлган иш бўлса, 'task' турига ажратинг.
Бошқа ҳолларда 'note' турига ажратинг.
Жавобни ҚАТЪИЙ JSON форматида беринг:
{"type": "expense/task/note", "response": "Фойдаланувчига қисқа ва фойдали жавоб (танланган тилда)"}

Тиллар бўйича қоида:
- lang_uz_cyr бўлса, кириллда жавоб беринг.
- lang_uz_lat бўлса, лотин алифбосида жавоб беринг.
- lang_ru бўлса, рус тилида жавоб беринг."""

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": text}]
        )

        raw_response = message.content[0].text
        # Extract JSON
        json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            note_type = data.get("type", "note")
            ai_response = data.get("response", raw_response)

            # Save to DB
            conn = sqlite3.connect("notes.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notes (user_id, type, content, timestamp) VALUES (?, ?, ?, ?)",
                (update.effective_user.id, note_type, text, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()

            final_text = f"✅ {ai_response}"
        else:
            final_text = f"🤖 {raw_response}"

        if wait_msg:
            await wait_msg.edit_text(final_text)
        else:
            await update.message.reply_text(final_text)

    except Exception as e:
        error_msg = f"❌ AI таҳлил хатоси: {str(e)}"
        if wait_msg:
            await wait_msg.edit_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msg = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

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
        await update.message.reply_text(msg["history_empty"])
        return

    history_text = msg["history_title"]
    for row in rows:
        ntype, content, ts = row
        history_text += f"📅 {ts[:16]} | [{ntype}] {content}\n"

    await update.message.reply_text(history_text)

async def generate_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msg = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    user_id = update.effective_user.id
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT type, content, timestamp FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(msg["history_empty"])
        return

    wait_msg = await update.message.reply_text(msg["summary_wait"])

    data_summary = "\n".join([f"{r[2]} | {r[0]}: {r[1]}" for r in rows])

    prompt = f"Қуйидаги маълумотларни таҳлил қилиб, фойдаланувчига қисқача хулоса беринг (харажатлар суммаси, бажарилган ишлар ва ҳ.к.):\n\n{data_summary}"

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system="Сиз таҳлилчисиз. Маълумотларни гуруҳлаб, фойдаланувчи тилида хулоса беринг.",
            messages=[{"role": "user", "content": prompt}]
        )
        await wait_msg.edit_text(f"{msg['summary_title']}\n\n{message.content[0].text}")
    except Exception as e:
        await wait_msg.edit_text(f"❌ Error: {str(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msg = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    voice = update.message.voice

    wait_msg = await update.message.reply_text(msg["wait_voice"])

    file = await context.bot.get_file(voice.file_id)
    ogg_path = f"voice_{voice.file_id}.ogg"
    wav_path = f"voice_{voice.file_id}.wav"

    try:
        await file.download_to_drive(ogg_path)

        # Convert OGG to WAV
        audio = AudioSegment.from_ogg(ogg_path)
        audio.export(wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)

        # Select STT language
        stt_lang = "uz-UZ" if lang.startswith("lang_uz") else "ru-RU"
        text = recognizer.recognize_google(audio_data, language=stt_lang)

        await wait_msg.edit_text(f"{msg['stt_prefix']}\n\n{text}\n\n{msg['wait_ai']}")
        await process_ai_request(update, context, text, wait_msg)

    except Exception as e:
        await wait_msg.edit_text(f"{msg['error_voice']} {str(e)}")
    finally:
        if os.path.exists(ogg_path): os.remove(ogg_path)
        if os.path.exists(wav_path): os.remove(wav_path)

def init_db():
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            content TEXT,
            timestamp DATETIME
        )
    """)
    conn.commit()
    conn.close()

def main():
    static_ffmpeg.add_paths()
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("summary", generate_summary))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
