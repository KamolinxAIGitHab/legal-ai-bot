import os
import re

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
        "confirmed": "✅ Тил танланди!\n\nДавлат харидлари, қонунчилик ёки молия бўйича саволингизни ёзинг:",
        "wait": "⏳ Жавоб тайёрланмоқда...",
        "error_api": "❌ API калит нотўғри. CLAUDE_API_KEY ни текширинг.",
        "error_limit": "❌ API лимити тугади. Кейинроқ уриниб кўринг.",
        "error_general": "❌ Хато юз берди. Кейинроқ уриниб кўринг.",
        "disclaimer": "⚠️ Жавоблар умумий ва таълимий мақсадда.",
    },
    "lang_uz_lat": {
        "confirmed": "✅ Til tanlandi!\n\nDavlat xaridlari, qonunchilik yoki moliya bo'yicha savolingizni yozing:",
        "wait": "⏳ Javob tayyorlanmoqda...",
        "error_api": "❌ API kalit noto'g'ri. CLAUDE_API_KEY ni tekshiring.",
        "error_limit": "❌ API limiti tugadi. Keyinroq urinib ko'ring.",
        "error_general": "❌ Xato yuz berdi. Keyinroq urinib ko'ring.",
        "disclaimer": "⚠️ Javoblar umumiy va ta'limiy maqsadda.",
    },
    "lang_ru": {
        "confirmed": "✅ Язык выбран!\n\nНапишите свой вопрос по госзакупкам, законодательству или финансам:",
        "wait": "⏳ Ответ готовится...",
        "error_api": "❌ Неверный API ключ. Проверьте CLAUDE_API_KEY.",
        "error_limit": "❌ Лимит API исчерпан. Попробуйте позже.",
        "error_general": "❌ Произошла ошибка. Попробуйте позже.",
        "disclaimer": "⚠️ Ответы носят общий и образовательный характер.",
    },
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(
        "Илтимос, тилни танланг / Iltimos, tilni tanlang / Пожалуйста, выберите язык:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang

    msg = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])["confirmed"]
    await query.edit_message_text(msg)

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
    messages = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])

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

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    loading_msg = await update.message.reply_text(messages["wait"])

    try:
        if not CLAUDE_API_KEY:
            await loading_msg.edit_text(messages["error_general"])
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)
        await loading_msg.edit_text(
            f"🤖 {answer}\n\n{messages['disclaimer']}"
        )

    except anthropic.AuthenticationError:
        await loading_msg.edit_text(messages["error_api"])
    except anthropic.RateLimitError:
        await loading_msg.edit_text(messages["error_limit"])
    except Exception as e:
        print(f"XATO TURI: {type(e).__name__}")
        print(f"XATO MATNI: {e}")
        await loading_msg.edit_text(messages["error_general"])

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
