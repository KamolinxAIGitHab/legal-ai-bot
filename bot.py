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

MESSAGES = {
    "lang_uz_cyr": {"chosen": "✅ Тил танланди!\n\nДавлат харидлари, қонунчилик ёки молия бўйича саволингизни ёзинг:", "wait": "⏳ Жавоб тайёрланмоқда...", "disc": "\n\n⚠️ Жавоблар умумий ва таълимий мақсадда.", "err": "❌ Хатолик юз берди.", "auth_err": "❌ API калит нотўғри. CLAUDE_API_KEY ни текширинг.", "limit_err": "❌ API лимити тугади. Кейинроқ уриниб кўринг."},
    "lang_uz_lat": {"chosen": "✅ Til tanlandi!\n\nDavlat xaridlari, qonunchilik yoki moliya bo'yicha savolingizni yozing:", "wait": "⏳ Javob tayyorlanmoqda...", "disc": "\n\n⚠️ Javoblar umumiy va ta'limiy maqsadda.", "err": "❌ Xatolik yuz berdi.", "auth_err": "❌ API kaliti noto'g'ri. CLAUDE_API_KEY ni tekshiring.", "limit_err": "❌ API limiti tugadi. Keyinroq urinib ko'ring."},
    "lang_ru": {"chosen": "✅ Язык выбран!\n\nНапишите ваш вопрос по госзакупкам или законодательству:", "wait": "⏳ Ответ готовится...", "disc": "\n\n⚠️ Ответы носят ознакомительный характер.", "err": "❌ Произошла ошибка.", "auth_err": "❌ Неверный API ключ. Проверьте CLAUDE_API_KEY.", "limit_err": "❌ Лимит API исчерпан. Попробуйте позже."}
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
    await query.edit_message_text(MESSAGES.get(lang, MESSAGES["lang_uz_cyr"])["chosen"])

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

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    m = MESSAGES.get(lang, MESSAGES["lang_uz_cyr"])
    wait_msg = await update.message.reply_text(m["wait"])

    try:
        if not CLAUDE_API_KEY:
            await wait_msg.edit_text("❌ CLAUDE_API_KEY error. Check Railway Variables.")
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)
        await wait_msg.edit_text(f"🤖 {answer}{m['disc']}")

    except anthropic.AuthenticationError:
        await wait_msg.edit_text(m["auth_err"])
    except anthropic.RateLimitError:
        await wait_msg.edit_text(m["limit_err"])
    except Exception as e:
        print(f"XATO: {e}")
        await wait_msg.edit_text(f"{m['err']}\n\n{str(e)[:100]}")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
