import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "success": "✅ Тил танланди!\n\nДавлат харидлари, қонунчилик ёки молия бўйича саволингизни ёзинг:",
        "waiting": "⏳ Жавоб тайёрланмоқда...",
        "error": "❌ Хато юз берди. Илтимос, қайта уриниб кўринг.",
        "disclaimer": "⚠️ Жавоблар умумий ва таълимий мақсадда."
    },
    "lang_uz_lat": {
        "success": "✅ Til tanlandi!\n\nDavlat xaridlari, qonunchilik yoki moliya bo'yicha savolingizni yozing:",
        "waiting": "⏳ Javob tayyorlanmoqda...",
        "error": "❌ Xato yuz berdi. Iltimos, qayta urinib ko'ring.",
        "disclaimer": "⚠️ Javoblar umumiy va ta'limiy maqsadda."
    },
    "lang_ru": {
        "success": "✅ Язык выбран!\n\nВведите ваш вопрос по государственным закупкам, законодательству или финансам:",
        "waiting": "⏳ Ответ готовится...",
        "error": "❌ Произошла ошибка. Пожалуйста, попробуйте еще раз.",
        "disclaimer": "⚠️ Ответы носят общий и образовательный характер."
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
    await query.edit_message_text(LOCALIZED_MESSAGES[lang]["success"])

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
5. Рақамли рўйхат билан аниқ жавоб беринг"""
    elif lang == "lang_uz_lat":
        system = "Siz O'zbekiston davlat xaridlari va qonunchilik bo'yicha mutaxasssissiz. O'zbek tilida lotin alifbosida javob bering."
    else:
        system = "Вы эксперт по государственным закупкам и законодательству Узбекистана. Отвечайте на русском языке."

    status_message = await update.message.reply_text(LOCALIZED_MESSAGES[lang]["waiting"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = message.content[0].text
        await status_message.edit_text(f"🤖 {answer}\n\n{LOCALIZED_MESSAGES[lang]['disclaimer']}")
    except Exception as e:
        await status_message.edit_text(LOCALIZED_MESSAGES[lang]["error"])

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
