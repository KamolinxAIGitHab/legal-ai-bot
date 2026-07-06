import os
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
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
    msg = "✅ Тил танланди!" if lang == "lang_uz_cyr" else "✅ Til tanlandi!" if lang == "lang_uz_lat" else "✅ Язык выбран!"
    await query.edit_message_text(f"{msg}\n\n" + (
        "Давлат харидлари, қонунчилик ёки молия бўйича саволингизни ёзинг:" if lang == "lang_uz_cyr" else
        "Davlat xaridlari, qonunchilik yoki moliya bo'yicha savolingizni yozing:" if lang == "lang_uz_lat" else
        "Напишите ваш вопрос по госзакупкам, законодательству или финансам:"
    ))

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

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    wait_msg = "⏳ Жавоб тайёрланмоқда..." if lang == "lang_uz_cyr" else "⏳ Javob tayyorlanmoqda..." if lang == "lang_uz_lat" else "⏳ Ответ готовится..."
    status_msg = await update.message.reply_text(wait_msg)

    try:
        if not CLAUDE_API_KEY:
            await update.message.reply_text(
                "❌ CLAUDE_API_KEY топилмади. Railway Variables ни текширинг."
            )
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)
        disclaimer = "⚠️ Жавоблар умумий ва таълимий мақсадда." if lang == "lang_uz_cyr" else "⚠️ Javoblar umumiy va ta'limiy maqsadda." if lang == "lang_uz_lat" else "⚠️ Ответы носят общий и ознакомительный характер."
        await status_msg.edit_text(f"🤖 {answer}\n\n{disclaimer}")

    except anthropic.AuthenticationError:
        await update.message.reply_text(
            "❌ API калит нотўғри. CLAUDE_API_KEY ни текширинг."
        )
    except anthropic.RateLimitError:
        await update.message.reply_text(
            "❌ API лимити тугади. Кейинроқ уриниб кўринг."
        )
    except Exception as e:
        print(f"XATO TURI: {type(e).__name__}")
        print(f"XATO MATNI: {e}")
        await update.message.reply_text(
            f"❌ Хато: {type(e).__name__}: {str(e)[:200]}"
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
