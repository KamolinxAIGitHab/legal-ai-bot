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
        "success": "✅ Тил танланди!\n\nДавлат харидлари, қонунчилик ёки молия бўйича саволингизни ёзинг:",
        "waiting": "⏳ Жавоб тайёрланмоқда...",
        "disclaimer": "⚠️ Жавоблар умумий ва таълимий мақсадда.",
        "error_api_key": "❌ CLAUDE_API_KEY топилмади. Railway Variables ни текширинг.",
        "error_auth": "❌ API калит нотўғри. CLAUDE_API_KEY ни текширинг.",
        "error_limit": "❌ API лимити тугади. Кейинроқ уриниб кўринг.",
        "error_generic": "❌ Хато: {error_type}: {error_msg}"
    },
    "lang_uz_lat": {
        "success": "✅ Til tanlandi!\n\nDavlat xaridlari, qonunchilik yoki moliya bo'yicha savolingizni yozing:",
        "waiting": "⏳ Javob tayyorlanmoqda...",
        "disclaimer": "⚠️ Javoblar umumiy va ta'limiy maqsadda.",
        "error_api_key": "❌ CLAUDE_API_KEY topilmadi. Railway Variables ni tekshiring.",
        "error_auth": "❌ API kalit noto'g'ri. CLAUDE_API_KEY ni tekshiring.",
        "error_limit": "❌ API limiti tugadi. Keyinroq urinib ko'ring.",
        "error_generic": "❌ Xato: {error_type}: {error_msg}"
    },
    "lang_ru": {
        "success": "✅ Язык выбран!\n\nВведите ваш вопрос по государственным закупкам, законодательству или финансам:",
        "waiting": "⏳ Ответ подготавливается...",
        "disclaimer": "⚠️ Ответы носят общий и ознакомительный характер.",
        "error_api_key": "❌ CLAUDE_API_KEY не найден. Проверьте Railway Variables.",
        "error_auth": "❌ Неверный ключ API. Проверьте CLAUDE_API_KEY.",
        "error_limit": "❌ Лимит API исчерпан. Попробуйте позже.",
        "error_generic": "❌ Ошибка: {error_type}: {error_msg}"
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
    success_text = LOCALIZED_MESSAGES.get(lang, LOCALIZED_MESSAGES["lang_uz_cyr"])["success"]
    await query.edit_message_text(success_text)

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
    waiting_msg = await update.message.reply_text(msgs["waiting"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        if not CLAUDE_API_KEY:
            await waiting_msg.edit_text(msgs["error_api_key"])
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)
        await waiting_msg.edit_text(
            f"🤖 {answer}\n\n{msgs['disclaimer']}"
        )

    except anthropic.AuthenticationError:
        await waiting_msg.edit_text(msgs["error_auth"])
    except anthropic.RateLimitError:
        await waiting_msg.edit_text(msgs["error_limit"])
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)[:200]
        print(f"XATO TURI: {error_type}")
        print(f"XATO MATNI: {e}")
        await waiting_msg.edit_text(
            msgs["error_generic"].format(error_type=error_type, error_msg=error_msg)
        )

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
