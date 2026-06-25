import os
import re
import base64
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic
import database

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

L = {
    "lang_uz_cyr": {
        "start": "Ассалому алайкум! Тилни танланг:",
        "chosen": "✅ Тайёр! Овозли хабар юборинг (харажат, иш, эслатма) ёки савол беринг:",
        "wait": "⏳ Ишланяпти...",
        "saved": "✅ Сақланди!\n\n🔹 Тури: {cat}\n🔹 Мазмуни: {text}\n🔹 Миқдор: {amt}",
        "stats_title": "📊 Охирги 24 соатдаги ҳисобот:",
        "total_exp": "💰 Жами харажат: {total} сўм",
        "reminders_title": "🔔 Сизнинг вазифаларингиз:",
        "no_data": "📭 Маълумот топилмади.",
        "error": "❌ Хатолик юз берди. Илтимос, қайтадан уриниб кўринг.",
        "legal_system": "Сиз Ўзбекистон қонунчилиги бўйича мутахассиссиз. Қисқа ва аниқ жавоб беринг."
    },
    "lang_uz_lat": {
        "start": "Assalomu alaykum! Tilni tanlang:",
        "chosen": "✅ Tayyor! Ovozli xabar yuboring (xarajat, ish, eslatma) yoki savol bering:",
        "wait": "⏳ Ishlanyapti...",
        "saved": "✅ Saqlandi!\n\n🔹 Turi: {cat}\n🔹 Mazmuni: {text}\n🔹 Miqdori: {amt}",
        "stats_title": "📊 Oxirgi 24 soatdagi hisobot:",
        "total_exp": "💰 Jami xarajat: {total} so'm",
        "reminders_title": "🔔 Sizning vazifalaringiz:",
        "no_data": "📭 Ma'lumot topilmadi.",
        "error": "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
        "legal_system": "Siz O'zbekiston qonunchiligi bo'yicha mutaxassissiz. Qisqa va aniq javob bering."
    },
    "lang_ru": {
        "start": "Здравствуйте! Выберите язык:",
        "chosen": "✅ Готово! Отправьте голосовое сообщение (расход, дело, заметка) или задайте вопрос:",
        "wait": "⏳ Обработка...",
        "saved": "✅ Сохранено!\n\n🔹 Тип: {cat}\n🔹 Содержание: {text}\n🔹 Сумма: {amt}",
        "stats_title": "📊 Отчет за последние 24 часа:",
        "total_exp": "💰 Всего расходов: {total} сум",
        "reminders_title": "🔔 Ваши задачи:",
        "no_data": "📭 Данных не найдено.",
        "error": "❌ Произошла ошибка. Пожалуйста, попробуйте еще раз.",
        "legal_system": "Вы эксперт по законодательству Узбекистана. Отвечайте кратко и ясно."
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(L["lang_uz_cyr"]["start"], reply_markup=InlineKeyboardMarkup(keyboard))

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    await query.edit_message_text(L[lang]["chosen"])

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    status_msg = await update.message.reply_text(L[lang]["wait"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)

    file = await update.message.voice.get_file()
    # Fixed unique filename to avoid collisions
    audio_path = f"voice_{update.effective_chat.id}_{update.message.message_id}.ogg"
    await file.download_to_drive(audio_path)

    try:
        with open(audio_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        system_prompt = (
            "Analyze the audio and extract: category (expense, task, or note), text (transcription), and amount (number, if expense). "
            "Return ONLY valid JSON. Languages: Uzbek (Cyrillic/Latin) or Russian."
        )

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "audio", "source": {"type": "base64", "media_type": "audio/ogg", "data": audio_data}},
                    {"type": "text", "text": "Extract data from this voice message."}
                ]
            }]
        )

        res_text = message.content[0].text
        json_match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")

        data = json.loads(json_match.group())

        database.add_record(update.effective_user.id, data.get('category', 'note'), data.get('text', ''), data.get('amount'))

        await status_msg.edit_text(L[lang]["saved"].format(
            cat=data.get('category', 'note'), text=data.get('text', ''), amt=data.get('amount', '-')
        ))

    except Exception as e:
        print(f"Error in handle_voice: {e}")
        await status_msg.edit_text(L[lang]["error"])
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    text = update.message.text

    # Fallback to legal AI bot logic
    await update.message.reply_text(L[lang]["wait"])
    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=L[lang]["legal_system"],
            messages=[{"role": "user", "content": text}]
        )
        await update.message.reply_text(message.content[0].text)
    except Exception as e:
        print(f"Error in handle_text: {e}")
        await update.message.reply_text(L[lang]["error"])

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id
    records = database.get_recent_records(user_id)
    total_exp = database.get_expenses_total(user_id)

    if not records:
        await update.message.reply_text(L[lang]["no_data"])
        return

    msg = f"{L[lang]['stats_title']}\n\n"
    for cat, content, amt, ts in records:
        amt_str = f" ({amt})" if amt else ""
        msg += f"• [{cat}] {content}{amt_str}\n"

    msg += f"\n{L[lang]['total_exp'].format(total=total_exp)}"
    await update.message.reply_text(msg)

async def reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    tasks = database.get_tasks(update.effective_user.id)

    if not tasks:
        await update.message.reply_text(L[lang]["no_data"])
        return

    msg = f"{L[lang]['reminders_title']}\n\n"
    for content, ts in tasks:
        msg += f"• {content} (📅 {ts})\n"

    await update.message.reply_text(msg)

def main():
    database.init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("reminders", reminders))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
