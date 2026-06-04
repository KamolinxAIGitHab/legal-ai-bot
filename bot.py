import os
import re
import asyncio
import io

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

VOICE_SYSTEM_PROMPT = """Сиз шахсий ёрдамчи ва кундалик қайдларни таҳлил қилувчи мутахассиссиз.
Фойдаланувчининг овозли хабари матнини таҳлил қилиб, уни қуйидаги тоифалардан бирига ажратинг:
1. Харажат (Expense) - агар пул сарфлангани ҳақида бўлса
2. Вазифа (Task) - агар бирор иш қилиш кераклиги ҳақида бўлса
3. Учрашув (Meeting) - агар ким биландир кўришиш ҳақида бўлса
4. Қайд (Note) - бошқа муҳим маълумотлар

Жавоб формати:
✅ [Тоифа номи]
📝 Қисқача мазмуни: ...
💰 Миқдори: (фақат харажат бўлса)
⏰ Вақти: (агар айтилган бўлса)

Қоидалар:
- Фақат фойдаланувчи танлаган тилда (Ўзбек ёки Рус) жавоб беринг.
- Markdown ишлатманг.
- Лўнда ва тушунарли бўлсин."""

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "wait": "⏳ Жавоб тайёрланмоқда...",
        "transcribing": "🎤 Овоз таҳлил қилинмоқда...",
        "analyzing": "🧠 Маълумот қайта ишланяпти...",
        "error_transcription": "❌ Овозни матнга айлантириб бўлмади.",
        "error_api": "❌ API билан боғланишда хатолик.",
        "welcome_voice": "✅ Тил танланди!\n\nСавол ёзишингиз ёки харажат, вазифа ва қайдларни овозли хабар орқали юборишингиз мумкин:"
    },
    "lang_uz_lat": {
        "wait": "⏳ Javob tayyorlanmoqda...",
        "transcribing": "🎤 Ovoz tahlil qilinmoqda...",
        "analyzing": "🧠 Ma'lumot qayta ishlanyapti...",
        "error_transcription": "❌ Ovozni matnga aylantirib bo'lmadi.",
        "error_api": "❌ API bilan bog'lanishda xatolik.",
        "welcome_voice": "✅ Til tanlandi!\n\nSavol yozishingiz yoki xarajat, vazifa va qaydlarni ovozli xabar orqali yuborishingiz mumkin:"
    },
    "lang_ru": {
        "wait": "⏳ Ответ готовится...",
        "transcribing": "🎤 Голос распознается...",
        "analyzing": "🧠 Данные обрабатываются...",
        "error_transcription": "❌ Не удалось распознать голос.",
        "error_api": "❌ Ошибка при обращении к API.",
        "welcome_voice": "✅ Язык выбран!\n\nВы можете написать вопрос или отправить голосовое сообщение о расходах, задачах и заметках:"
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
    await query.edit_message_text(msgs["welcome_voice"])

def self_record_audio(wav_path, recognizer):
    with sr.AudioFile(wav_path) as source:
        return recognizer.record(source)

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

    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    await update.message.reply_text(msgs["wait"])

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

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

    status_msg = await update.message.reply_text(msgs["transcribing"])

    try:
        voice_file = await update.message.voice.get_file()
        ogg_path = f"voice_messages/{voice_file.file_id}.ogg"
        wav_path = f"voice_messages/{voice_file.file_id}.wav"

        await voice_file.download_to_drive(ogg_path)

        audio = await asyncio.to_thread(AudioSegment.from_ogg, ogg_path)
        await asyncio.to_thread(audio.export, wav_path, format="wav")

        recognizer = sr.Recognizer()
        audio_data = await asyncio.to_thread(self_record_audio, wav_path, recognizer)

        stt_lang = "uz-UZ" if "uz" in lang else "ru-RU"
        text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language=stt_lang)

        await status_msg.edit_text(msgs["analyzing"])

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=VOICE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}]
        )

        answer = clean_markdown(message.content[0].text)
        await status_msg.edit_text(f"🤖 {answer}")

    except sr.UnknownValueError:
        await status_msg.edit_text(msgs["error_transcription"])
    except Exception as e:
        print(f"VOICE ERROR: {e}")
        await status_msg.edit_text(f"{msgs['error_api']} {str(e)[:100]}")
    finally:
        for p in [ogg_path, wav_path]:
            if 'ogg_path' in locals() and os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass

def main():
    os.makedirs('voice_messages', exist_ok=True)
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
