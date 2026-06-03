import os
import re
import io
import asyncio
import speech_recognition as sr
from pydub import AudioSegment
import static_ffmpeg

static_ffmpeg.add_paths()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

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
        "✅ Тил танланди!\n\nДавлат харидлари, қонунчилик ёки молия бўйича саволингизни ёзинг:"
    )

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

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")

    wait_msg = await update.message.reply_text("⏳ Овозли хабар юкланмоқда...")

    try:
        voice_file = await update.message.voice.get_file()
        voice_data = await voice_file.download_as_bytearray()

        # Convert OGG to WAV
        await wait_msg.edit_text("⏳ Овозни қайта ишлаш...")
        ogg_io = io.BytesIO(voice_data)
        audio = await asyncio.to_thread(AudioSegment.from_file, ogg_io, format="ogg")
        wav_io = io.BytesIO()
        await asyncio.to_thread(audio.export, wav_io, format="wav")
        wav_io.seek(0)

        # Transcribe
        await wait_msg.edit_text("⏳ Матнга айлантириш...")
        recognizer = sr.Recognizer()

        # Determine transcription language
        stt_lang = "uz-UZ"
        if lang == "lang_ru":
            stt_lang = "ru-RU"

        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)
            text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=stt_lang)

        await wait_msg.edit_text("⏳ Таҳлил қилинмоқда...")

        if lang == "lang_uz_cyr":
            system = """Сиз шахсий ёрдамчисиз. Овозли хабар матнини таҳлил қилинг ва:
1. Хабар турини аниқланг (харажат, режа, эслатма, ғоя ва ҳ.к.).
2. Муҳим маълумотларни ажратиб кўрсатинг (сумма, вақт, макон).
3. Қисқа ва тушунарли хулоса беринг.
Фақат кирилл алифбосида жавоб беринг. Markdown ишлатманг."""
        elif lang == "lang_uz_lat":
            system = """Siz shaxsiy yordamchisiz. Ovozli xabar matnini tahlil qiling va:
1. Xabar turini aniqlang (xarajat, reja, eslatma, g'oya va h.k.).
2. Muhim ma'lumotlarni ajratib ko'rsating (summa, vaqt, makon).
3. Qisqa va tushunarli xulosa bering.
Faqat lotin alifbosida javob bering. Markdown ishlatmang."""
        else:
            system = """Вы личный помощник. Проанализируйте текст голосового сообщения и:
1. Определите тип сообщения (расход, план, заметка, идея и т.д.).
2. Выделите важные детали (сумма, время, место).
3. Дайте краткий и понятный итог.
Не используйте Markdown."""

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": f"Матн: {text}"}]
        )
        answer = clean_markdown(message.content[0].text)

        await wait_msg.edit_text(f"📝 Текст: {text}\n\n🤖 Таҳлил:\n{answer}")

    except Exception as e:
        await wait_msg.edit_text(f"❌ Хато: {str(e)}")

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
