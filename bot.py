import os
import re
import base64
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic
import database

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "start": "Илтимос, тилни танланг:",
        "selected": "✅ Тил танланди!\n\nСавол ёзинг ёки овозли хабар юборинг (харажатлар, вазифалар ёки эслатмалар учун):",
        "wait": "⏳ Жавоб тайёрланмоқда...",
        "processing": "🎙 Овоз таҳлил қилинмоқда...",
        "saved": "✅ Сақланди!\n\n📂 Тур: {category}\n📝 Мазмун: {content}\n💰 Миқдор: {amount}",
        "report_header": "📊 Сўнгги ёзувлар:\n\n",
        "err_api": "❌ API калит нотўғри.",
        "err_limit": "❌ API лимити тугади.",
        "err_generic": "❌ Хато юз берди.",
        "expense": "Харажат",
        "task": "Вазифа",
        "note": "Эслатма"
    },
    "lang_uz_lat": {
        "start": "Iltimos, tilni tanlang:",
        "selected": "✅ Til tanlandi!\n\nSavol yozing yoki ovozli xabar yuboring (xarajatlar, vazifalar yoki eslatmalar uchun):",
        "wait": "⏳ Javob tayyorlanmoqda...",
        "processing": "🎙 Ovoz tahlil qilinmoqda...",
        "saved": "✅ Saqlandi!\n\n📂 Tur: {category}\n📝 Mazmun: {content}\n💰 Miqdor: {amount}",
        "report_header": "📊 So'nggi yozuvlar:\n\n",
        "err_api": "❌ API kalit noto'g'ri.",
        "err_limit": "❌ API limiti tugadi.",
        "err_generic": "❌ Xato yuz berdi.",
        "expense": "Xarajat",
        "task": "Vazifa",
        "note": "Eslatma"
    },
    "lang_ru": {
        "start": "Пожалуйста, выберите язык:",
        "selected": "✅ Язык выбран!\n\nЗадайте вопрос или отправьте голосовое сообщение (для расходов, задач или заметок):",
        "wait": "⏳ Ответ готовится...",
        "processing": "🎙 Анализ голоса...",
        "saved": "✅ Сохранено!\n\n📂 Тип: {category}\n📝 Содержание: {content}\n💰 Сумма: {amount}",
        "report_header": "📊 Последние записи:\n\n",
        "err_api": "❌ Неверный API ключ.",
        "err_limit": "❌ Лимит API исчерпан.",
        "err_generic": "❌ Произошла ошибка.",
        "expense": "Расход",
        "task": "Задача",
        "note": "Заметка"
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(
        LOCALIZED_MESSAGES["lang_uz_cyr"]["start"],
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    await query.edit_message_text(LOCALIZED_MESSAGES[lang]["selected"])

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
    L = LOCALIZED_MESSAGES[lang]

    if lang == "lang_uz_cyr":
        system = "Сиз фойдали ёрдамчисиз. Фойдаланувчига саволларига жавоб беришда ёрдам беринг. Кирилл алифбосида, Markdown ишлатмай жавоб беринг."
    elif lang == "lang_uz_lat":
        system = "Siz foydali yordamchisiz. Foydalanuvchiga savollariga javob berishda yordam bering. Lotin alifbosida, Markdown ishlatmay javob bering."
    else:
        system = "Вы полезный помощник. Помогайте пользователю ответами на его вопросы. Отвечайте на русском, без Markdown."

    status_msg = await update.message.reply_text(L["wait"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)
        await status_msg.edit_text(f"🤖 {answer}")
    except Exception as e:
        await status_msg.edit_text(f"{L['err_generic']} {str(e)[:100]}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    L = LOCALIZED_MESSAGES[lang]

    status_msg = await update.message.reply_text(L["processing"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    file_path = None
    try:
        voice = await update.message.voice.get_file()
        file_path = f"voice_{update.effective_user.id}_{update.message.message_id}.ogg"
        await voice.download_to_drive(file_path)

        with open(file_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = (
            "Analyze this audio and return only valid JSON with these keys: "
            "category (must be one of: expense, task, note), "
            "content (summary of the message), "
            "amount (number for expense, else null)."
        )

        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "audio", "source": {"type": "base64", "media_type": "audio/ogg", "data": audio_data}},
                    {"type": "text", "text": prompt}
                ]
            }]
        )

        raw_text = response.content[0].text
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")

        data = json.loads(json_match.group())

        database.add_record(
            user_id=update.effective_user.id,
            category=data.get("category"),
            content=data.get("content"),
            amount=data.get("amount")
        )

        await status_msg.edit_text(L["saved"].format(
            category=L.get(data.get("category"), data.get("category")),
            content=data.get("content"),
            amount=data.get("amount") or "---"
        ))

    except Exception as e:
        await status_msg.edit_text(f"{L['err_generic']} {str(e)[:100]}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    L = LOCALIZED_MESSAGES[lang]
    records = database.get_recent_records(update.effective_user.id)

    if not records:
        await update.message.reply_text("📭")
        return

    text = L["report_header"]
    for cat, content, amount, ts in records:
        text += f"📅 {ts[:16]} | 📂 {L.get(cat, cat)}\n📝 {content}"
        if amount: text += f" | 💰 {amount}"
        text += "\n\n"

    await update.message.reply_text(text)

def main():
    database.init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
