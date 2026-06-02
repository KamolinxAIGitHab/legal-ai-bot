import os
import re
import asyncio
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

# Ensure storage directory exists
VOICE_DIR = "voice_messages"
if not os.path.exists(VOICE_DIR):
    os.makedirs(VOICE_DIR)

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "wait": "⏳ Кутинг...",
        "transcribing": "🎤 Овоз эшитилмоқда ва матнга айлантирилмоқда...",
        "analyzing": "🧐 Таҳлил қилинмоқда...",
        "error_api": "❌ API калит топилмади.",
        "error_transcription": "❌ Овозни матнга айлантиришда хатолик юз берди.",
        "welcome": "Илтимос, тилни танланг:",
        "instruction": "✅ Тил танланди!\n\nЭнди сиз харажатларингиз, вазифаларингиз ёки ҳуқуқий саволларингизни матн ёки овозли хабар кўринишида юборишингиз мумкин."
    },
    "lang_uz_lat": {
        "wait": "⏳ Kuting...",
        "transcribing": "🎤 Ovoz eshitilmoqda va matnga aylantirilmoqda...",
        "analyzing": "🧐 Tahlil qilinmoqda...",
        "error_api": "❌ API kalit topilmadi.",
        "error_transcription": "❌ Ovozni matnga aylantirishda xatolik yuz berdi.",
        "welcome": "Iltimos, tilni tanlang:",
        "instruction": "✅ Til tanlandi!\n\nEndi siz xarajatlaringiz, vazifalaringiz yoki huquqiy savollaringizni matn yoki ovozli xabar ko'rinishida yuborishingiz mumkin."
    },
    "lang_ru": {
        "wait": "⏳ Подождите...",
        "transcribing": "🎤 Слушаю и расшифровываю голос...",
        "analyzing": "🧐 Анализирую...",
        "error_api": "❌ API ключ не найден.",
        "error_transcription": "❌ Произошла ошибка при расшифровке голоса.",
        "welcome": "Пожалуйста, выберите язык:",
        "instruction": "✅ Язык выбран!\n\nТеперь вы можете отправлять свои расходы, задачи или юридические вопросы в виде текста или голосового сообщения."
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(
        "Ассалому алайкум! Тилни танланг / Выберите язык:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    await query.edit_message_text(LOCALIZED_MESSAGES[lang]["instruction"])

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def get_ai_response(text: str, lang: str):
    if lang == "lang_uz_cyr":
        system = """Сиз шахсий ёрдамчисиз. Фойдаланувчига кундалик ишларини бошқаришда, харажатларни таҳлил қилишда ва эслатмаларни тартибга солишда ёрдам беринг.
Қатъий қоидалар:
1. Фақат ўзбек тилида, кирилл алифбосида ёзинг
2. Markdown белгиларини ИШЛАТМАНГ
3. Харажатлар айтилса, уларни тоифаларга (овқат, транспорт ва ҳ.к.) ажратинг ва умумий суммани ҳисобланг
4. Вазифалар бўлса, уларни муҳимлик даражасига кўра тартибланг"""

    elif lang == "lang_uz_lat":
        system = """Siz shaxsiy yordamchisiz. Foydalanuvchiga kundalik ishlarini boshqarishda, xarajatlarni tahlil qilishda va eslatmalarni tartibga solishda yordam bering.
Qoidalar:
1. O'zbek tilida lotin alifbosida javob bering
2. Markdown belgilarini ISHLATMANG
3. Xarajatlar aytilsa, ularni toifalarga (ovqat, transport va h.k.) ajrating va umumiy summani hisoblang
4. Vazifalar bo'lsa, ularni muhimlik darajasiga ko'ra tartiblang"""

    else:
        system = """Вы личный помощник. Помогайте пользователю управлять повседневными делами, анализировать расходы и организовывать заметки.
Правила:
1. Отвечайте на русском языке
2. НЕ используйте Markdown
3. Если указаны расходы, распределите их по категориям (еда, транспорт и т.д.) и подсчитайте общую сумму
4. Если указаны задачи, упорядочите их по приоритетности"""

    if not CLAUDE_API_KEY:
        return "ERROR_API"

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": text}]
        )
        return clean_markdown(message.content[0].text)
    except Exception as e:
        return f"ERROR: {str(e)}"

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    question = update.message.text

    wait_msg = await update.message.reply_text(LOCALIZED_MESSAGES[lang]["wait"])

    answer = await get_ai_response(question, lang)

    if answer == "ERROR_API":
        await wait_msg.edit_text(LOCALIZED_MESSAGES[lang]["error_api"])
    elif answer.startswith("ERROR:"):
        await wait_msg.edit_text(f"❌ {answer}")
    else:
        await wait_msg.edit_text(f"🤖 {answer}\n\n⚠️ Жавоблар умумий ва таълимий мақсадда.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")

    status_msg = await update.message.reply_text(LOCALIZED_MESSAGES[lang]["transcribing"])

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    ogg_path = f"voice_messages/{voice.file_id}.ogg"
    wav_path = f"voice_messages/{voice.file_id}.wav"

    await file.download_to_drive(ogg_path)

    try:
        # Convert OGG to WAV
        audio = await asyncio.to_thread(AudioSegment.from_file, ogg_path)
        await asyncio.to_thread(audio.export, wav_path, format="wav")

        # Transcribe
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)

        transcription = await asyncio.to_thread(
            recognizer.recognize_google, audio_data, language="uz-UZ" if "uz" in lang else "ru-RU"
        )

        await status_msg.edit_text(LOCALIZED_MESSAGES[lang]["analyzing"])

        answer = await get_ai_response(transcription, lang)

        if answer == "ERROR_API":
            await status_msg.edit_text(LOCALIZED_MESSAGES[lang]["error_api"])
        elif answer.startswith("ERROR:"):
            await status_msg.edit_text(f"❌ {answer}")
        else:
            final_text = f"📝 {transcription}\n\n🤖 {answer}\n\n⚠️ Жавоблар умумий ва таълимий мақсадда."
            await status_msg.edit_text(final_text)

    except sr.UnknownValueError:
        await status_msg.edit_text(LOCALIZED_MESSAGES[lang]["error_transcription"])
    except Exception as e:
        await status_msg.edit_text(f"❌ Хатолик: {str(e)}")
    finally:
        if os.path.exists(ogg_path): os.remove(ogg_path)
        if os.path.exists(wav_path): os.remove(wav_path)

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
