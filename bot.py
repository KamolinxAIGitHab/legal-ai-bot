from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = "8498913508:AAE_1SUaaT253uPnqNksryg1A5VVx-tbZww"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("Oʻzbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Илтимос, тилни танланг / Пожалуйста, выберите язык:",
        reply_markup=reply_markup,
    )


async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["lang"] = query.data

    await query.edit_message_text(
        "Раҳмат. Энди саволингизни ёзинг.\n\n"
        "⚠️ Эслатма: жавоблар умумий ва таълимий мақсадда."
    )


async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang")

    if not lang:
        await update.message.reply_text("Илтимос, аввал /start босиб тилни танланг.")
        return

    context.user_data["question"] = update.message.text

    keyboard = [
        [InlineKeyboardButton("🇺🇿 Ўзбекистон", callback_data="jur_uz")],
        [InlineKeyboardButton("🌍 Бошқа давлат", callback_data="jur_other")],
        [InlineKeyboardButton("📚 Умумий маълумот", callback_data="jur_general")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Саволингиз қайси мамлакат қонунчилигига тегишли?",
        reply_markup=reply_markup,
    )


async def jurisdiction_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["jurisdiction"] = query.data

    await query.edit_message_text(
        "Раҳмат. Саволингиз қабул қилинди.\n\n"
        "Жавоб умумий ва таълимий мақсадда тайёрланади."
    )


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(CallbackQueryHandler(jurisdiction_chosen, pattern="^jur_"))

    print("Бот ишга тушди...")
    app.run_polling()


if __name__ == "__main__":
    main()
