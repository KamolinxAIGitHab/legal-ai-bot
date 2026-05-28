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

    messages = {
        "lang_uz_cyr": "✅ Тил танланди!\n\nДавлат харидлари, қонунчилик ёки молия бўйича саволингизни ёзинг:",
        "lang_uz_lat": "✅ Til tanlandi!\n\nDavlat xaridlari, qonunchilik yoki moliya bo'yicha savolingizni yozing:",
        "lang_ru": "✅ Язык выбран!\n\nНапишите ваш вопрос по государственным закупкам, законодательству или финансам:"
    }

    await query.edit_message_text(messages.get(lang, messages["lang_uz_cyr"]))

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

    wait_texts = {
        "lang_uz_cyr": "⏳ Жавоб тайёрланмоқда...",
        "lang_uz_lat": "⏳ Javob tayyorlanmoqda...",
        "lang_ru": "⏳ Ответ готовится..."
    }
    wait_message = await update.message.reply_text(wait_texts.get(lang, wait_texts["lang_uz_cyr"]))

    try:
        if not CLAUDE_API_KEY:
            error_msgs = {
                "lang_uz_cyr": "❌ CLAUDE_API_KEY топилмади.",
                "lang_uz_lat": "❌ CLAUDE_API_KEY topilmadi.",
                "lang_ru": "❌ CLAUDE_API_KEY не найден."
            }
            await wait_message.edit_text(error_msgs.get(lang, error_msgs["lang_uz_cyr"]))
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)

        disclaimers = {
            "lang_uz_cyr": "⚠️ Жавоблар умумий ва таълимий мақсадда.",
            "lang_uz_lat": "⚠️ Javoblar umumiy va ta'limiy maqsadda.",
            "lang_ru": "⚠️ Ответы носят общий и образовательный характер."
        }

        await wait_message.edit_text(
            f"🤖 {answer}\n\n{disclaimers.get(lang, disclaimers['lang_uz_cyr'])}"
        )

    except anthropic.AuthenticationError:
        auth_errors = {
            "lang_uz_cyr": "❌ API калит нотўғри.",
            "lang_uz_lat": "❌ API kalit noto'g'ri.",
            "lang_ru": "❌ Неверный API ключ."
        }
        await wait_message.edit_text(auth_errors.get(lang, auth_errors["lang_uz_cyr"]))
    except anthropic.RateLimitError:
        limit_errors = {
            "lang_uz_cyr": "❌ API лимити тугади. Кейинроқ уриниб кўринг.",
            "lang_uz_lat": "❌ API limiti tugadi. Keyinroq urinib ko'ring.",
            "lang_ru": "❌ Лимит API исчерпан. Попробуйте позже."
        }
        await wait_message.edit_text(limit_errors.get(lang, limit_errors["lang_uz_cyr"]))
    except Exception as e:
        print(f"XATO TURI: {type(e).__name__}")
        print(f"XATO MATNI: {e}")
        generic_errors = {
            "lang_uz_cyr": "❌ Хато",
            "lang_uz_lat": "❌ Xato",
            "lang_ru": "❌ Ошибка"
        }
        await wait_message.edit_text(
            f"{generic_errors.get(lang, generic_errors['lang_uz_cyr'])}: {type(e).__name__}: {str(e)[:200]}"
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
