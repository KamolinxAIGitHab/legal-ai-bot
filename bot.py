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
        "lang_selected": "✅ Тил танланди!\n\nДавлат харидлари, қонунчилик ёки молия бўйича саволингизни ёзинг:",
        "wait": "⏳ Жавоб тайёрланмоқда...",
        "warn": "⚠️ Жавоблар умумий ва таълимий мақсадда.",
        "err": "❌ Хато юз берди. Қайта уриниб кўринг.",
    },
    "lang_uz_lat": {
        "lang_selected": "✅ Til tanlandi!\n\nSavolingizni yozing:",
        "wait": "⏳ Javob tayyorlanmoqda...",
        "warn": "⚠️ Javoblar umumiy va ta'limiy maqsadda.",
        "err": "❌ Xato yuz berdi. Qayta urinib ko'ring.",
    },
    "lang_ru": {
        "lang_selected": "✅ Язык выбран!\n\nВведите ваш вопрос:",
        "wait": "⏳ Ответ готовится...",
        "warn": "⚠️ Ответы носят общий характер.",
        "err": "❌ Ошибка. Попробуйте еще раз.",
    },
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
    msg = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])["lang_selected"]
    await query.edit_message_text(msg)

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

    msgs = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status_msg = await update.message.reply_text(msgs["wait"])

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        await status_msg.edit_text(f"🤖 {message.content[0].text}\n\n{msgs['warn']}")
    except Exception:
        await status_msg.edit_text(msgs["err"])

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
