import os
import re
import base64
import json
import database

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

L = {
    "lang_uz_cyr": {
        "ok": "✅ Сақланди!", "wait": "⏳ Илтимос, кутинг...", "err": "❌ Хатолик юз берди.",
        "note": "Эслатма", "expense": "Харажат", "task": "Вазифа"
    },
    "lang_uz_lat": {
        "ok": "✅ Saqlandi!", "wait": "⏳ Iltimos, kuting...", "err": "❌ Xatolik yuz berdi.",
        "note": "Eslatma", "expense": "Xarajat", "task": "Vazifa"
    },
    "lang_ru": {
        "ok": "✅ Сохранено!", "wait": "⏳ Пожалуйста, подождите...", "err": "❌ Произошла ошибка.",
        "note": "Заметка", "expense": "Расход", "task": "Задача"
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
    context.user_data["lang"] = query.data
    await query.edit_message_text(
        "✅ Тил танланди!\n\nДавлат харидлари, қонунчилик ёки молия бўйича саволингизни ёзинг:"
    )

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

    await update.message.reply_text("⏳ Жавоб тайёрланмоқда...")

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
        await update.message.reply_text(
            f"🤖 {answer}\n\n⚠️ Жавоблар умумий ва таълимий мақсадда."
        )

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

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    status_msg = await update.message.reply_text(L[lang]["wait"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    voice_path = f"voice_{update.effective_chat.id}_{update.message.message_id}.ogg"
    try:
        voice = await update.message.voice.get_file()
        await voice.download_to_drive(voice_path)

        with open(voice_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = "Analyze the voice and return JSON with keys: category (expense/task/note), content, amount (number or null)."

        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=512,
            system=prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Process this voice memo:"},
                    {"type": "audio", "source": {"type": "base64", "media_type": "audio/ogg", "data": audio_data}}
                ]
            }]
        )

        match = re.search(r'\{.*\}', response.content[0].text, re.DOTALL)
        if not match:
            raise ValueError("Invalid AI response")

        res = json.loads(match.group())
        database.save_record(update.effective_user.id, res['category'], res['content'], res.get('amount'))

        cat_label = L[lang].get(res['category'], res['category'])
        await status_msg.edit_text(f"{L[lang]['ok']}\n\n📂 {cat_label}: {res['content']}")

    except Exception as e:
        print(f"VOICE ERR: {e}")
        await status_msg.edit_text(L[lang]["err"])
    finally:
        if os.path.exists(voice_path):
            os.remove(voice_path)

def main():
    database.init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
