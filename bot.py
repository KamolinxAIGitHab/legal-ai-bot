import os
import re
import sqlite3
import json
import asyncio
from datetime import datetime
import speech_recognition as sr
import static_ffmpeg
static_ffmpeg.add_paths()
from pydub import AudioSegment

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
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(
        "Илтимос, тилни танланг: / Пожалуйста, выберите язык: / Iltimos, tilni tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    cursor.execute("SELECT type, content, timestamp FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Тарих бўш. / История пуста.")
        return

    text = "📋 Сўнгги 10 та қайд:\n\n"
    for r in rows:
        text += f"🔹 [{r[0].upper()}] ({r[2][:10]}): {r[1][:50]}...\n"
    await update.message.reply_text(text)

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()
    # Limit to last 50 notes to avoid token limits and keep it relevant
    cursor.execute("SELECT type, content FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Маълумот йўқ. / Нет данных.")
        return

    wait_msg = await update.message.reply_text("⏳...")

    data_str = "\n".join([f"{r[0]}: {r[1]}" for r in rows])

    system_prompt = "Provide a brief summary of the user's recorded notes and expenses in " + ("Uzbek (Cyrillic)" if lang == "lang_uz_cyr" else "Uzbek (Latin)" if lang == "lang_uz_lat" else "Russian")

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Analyze these notes and provide a summary:\n{data_str}"}]
        )
        await wait_msg.edit_text(f"📊 {message.content[0].text}")
    except Exception as e:
        await wait_msg.edit_text(f"❌ Error: {str(e)}")

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["lang"] = query.data
    await query.edit_message_text(
        "✅ Тил танланди!\n\nДавлат харидлари, қонунчилик ёки молия бўйича саволингизни ёзинг:"
    )

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

    wait_msg = await update.message.reply_text("🎤 Овоз ёзиб олиняпти..." if lang == "lang_uz_cyr" else "🎤 Ovoz yozib olinyapti..." if lang == "lang_uz_lat" else "🎤 Голос записывается...")

    file = await context.bot.get_file(voice.file_id)
    ogg_path = f"voice_{voice.file_id}.ogg"
    wav_path = f"voice_{voice.file_id}.wav"

    try:
        await file.download_to_drive(ogg_path)

        # OGG to WAV conversion
        audio = await asyncio.to_thread(AudioSegment.from_ogg, ogg_path)
        await asyncio.to_thread(audio.export, wav_path, format="wav")

        # Transcription
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)

        stt_lang = 'uz-UZ' if 'uz' in lang else 'ru-RU'
        text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=stt_lang)

        await wait_msg.edit_text(f"📝 Текст: {text}\n\n⏳ Анализ қилиняпти..." if lang == "lang_uz_cyr" else f"📝 Matn: {text}\n\n⏳ Analiz qilinyapti..." if lang == "lang_uz_lat" else f"📝 Текст: {text}\n\n⏳ Анализируется...")

        await process_ai_request(update, context, text, wait_msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Хато: {str(e)}")
    finally:
        if os.path.exists(ogg_path): os.remove(ogg_path)
        if os.path.exists(wav_path): os.remove(wav_path)

async def process_ai_request(update, context, text, wait_msg):
    lang = context.user_data.get("lang", "lang_uz_cyr")

    system_prompt = """You are a smart personal assistant. Analyze the user's voice note/text.
Categorize it into: 'expense', 'task', 'legal', or 'note'.
Return ONLY a JSON string like this:
{"type": "category", "response": "Short, clear summary/answer in the user's language"}

User Language: """ + ("Uzbek (Cyrillic)" if lang == "lang_uz_cyr" else "Uzbek (Latin)" if lang == "lang_uz_lat" else "Russian")

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": text}]
        )

        raw_response = message.content[0].text
        json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)

        if json_match:
            data = json_match.group()
            result = json.loads(data)

            # Save to DB
            conn = sqlite3.connect("notes.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notes (user_id, type, content, timestamp) VALUES (?, ?, ?, ?)",
                (update.effective_user.id, result['type'], text, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()

            await wait_msg.edit_text(f"✅ {result['type'].upper()}: {result['response']}")
        else:
            await wait_msg.edit_text(f"🤖 {raw_response}")

    except Exception as e:
        await wait_msg.edit_text(f"❌ Error: {str(e)}")

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    question = update.message.text

    # Prompt user to choose between personal assistant and legal specialist if not obvious
    is_formal = any(kw in question.lower() for kw in ['қарор', 'қонун', 'низом', 'qonun', 'qaror', 'zakon', 'давлат харидлари', 'xarid'])

    if len(question.split()) > 10 or is_formal:
        await handle_legal_question(update, context, question)
    else:
        wait_msg = await update.message.reply_text("⏳...")
        await process_ai_request(update, context, question, wait_msg)

async def handle_legal_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str):
    lang = context.user_data.get("lang", "lang_uz_cyr")

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
            model="claude-sonnet-4-5",
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
