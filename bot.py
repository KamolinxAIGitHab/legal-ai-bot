import os
import re
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic
import database
import transcription

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
CLAUDE_MODEL = "claude-3-5-sonnet-20240620"

LOCALIZED_MESSAGES = {
    "lang_uz_cyr": {
        "start": "Тилни танланг:",
        "chosen": "✅ Тил танланди! Энди овозли хабар ёки матн юборишингиз мумкин. Мен харажатларни, вазифаларни ва қайдларни сақлайман.",
        "wait": "⏳ Ишлаяпман...",
        "transcribing": "🎤 Овозни матнга айлантиряпман...",
        "analyzing": "🧠 Таҳлил қиляпман...",
        "saved": "✅ Сақланди!",
        "error": "❌ Хатолик юз берди.",
        "summary_title": "📊 Бугунги ҳисобот:",
        "no_data": "Бугунча маълумот йўқ.",
        "history_title": "📜 Охирги қайдлар:",
        "expenses": "💰 Харажатлар:",
        "tasks": "✅ Вазифалар:",
    },
    "lang_uz_lat": {
        "start": "Tilni tanlang:",
        "chosen": "✅ Til tanlandi! Endi ovozli xabar yoki matn yuborishingiz mumkin. Men xarajatlarni, vazifalarni va qaydlarni saqlayman.",
        "wait": "⏳ Ishlayapman...",
        "transcribing": "🎤 Ovozni matnga aylantiryapman...",
        "analyzing": "🧠 Tahlil qilyapman...",
        "saved": "✅ Saqlandi!",
        "error": "❌ Xatolik yuz berdi.",
        "summary_title": "📊 Bugungi hisobot:",
        "no_data": "Buguncha ma'lumot yo'q.",
        "history_title": "📜 Oxirgi qaydlar:",
        "expenses": "💰 Xarajatlar:",
        "tasks": "✅ Vazifalar:",
    },
    "lang_ru": {
        "start": "Выберите язык:",
        "chosen": "✅ Язык выбран! Теперь вы можете отправлять голосовые сообщения или текст. Я сохраню расходы, задачи и заметки.",
        "wait": "⏳ Обработка...",
        "transcribing": "🎤 Расшифровка голоса...",
        "analyzing": "🧠 Анализирую...",
        "saved": "✅ Сохранено!",
        "error": "❌ Произошла ошибка.",
        "summary_title": "📊 Отчет за сегодня:",
        "no_data": "На сегодня данных нет.",
        "history_title": "📜 Последние записи:",
        "expenses": "💰 Расходы:",
        "tasks": "✅ Задачи:",
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(
        "Ассалому алайкум! Илтимос, тилни танланг / Пожалуйста, выберите язык:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    await query.edit_message_text(LOCALIZED_MESSAGES[lang]["chosen"])

def get_system_prompt(lang):
    prompts = {
        "lang_uz_cyr": "Сиз фойдали ёрдамчисиз. Фойдаланувчининг овозли ёки матнли хабаридан маълумотни ажратиб олинг ва фақат JSON форматида қайтаринг. JSON майдонлари: 'type' (expense, task, note), 'amount' (рақам ёки null), 'currency' (UZS, USD ёки null), 'category' (умумий категория), 'content' (қисқача мазмуни). Масалан: 'Тушликка 25000 сўм ишлатдим' -> {'type': 'expense', 'amount': 25000, 'currency': 'UZS', 'category': 'food', 'content': 'Тушлик'}",
        "lang_uz_lat": "Siz foydali yordamchisiz. Foydalanuvchining ovozli yoki matnli xabaridan ma'lumotni ajratib oling va faqat JSON formatida qaytaring. JSON maydonlari: 'type' (expense, task, note), 'amount' (raqam yoki null), 'currency' (UZS, USD yoki null), 'category' (umumiy kategoriya), 'content' (qisqacha mazmuni). Masalan: 'Tushlikka 25000 so'm ishlatdim' -> {'type': 'expense', 'amount': 25000, 'currency': 'UZS', 'category': 'food', 'content': 'Tushlik'}",
        "lang_ru": "Вы полезный помощник. Извлеките информацию из голосового или текстового сообщения пользователя и верните только в формате JSON. Поля JSON: 'type' (expense, task, note), 'amount' (число или null), 'currency' (UZS, USD или null), 'category' (общая категория), 'content' (краткое содержание). Пример: 'Потратил 25000 сум на обед' -> {'type': 'expense', 'amount': 25000, 'currency': 'UZS', 'category': 'food', 'content': 'Обед'}"
    }
    return prompts.get(lang, prompts["lang_uz_cyr"])

async def process_entry(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msg = await update.message.reply_text(LOCALIZED_MESSAGES[lang]["analyzing"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=get_system_prompt(lang),
            messages=[{"role": "user", "content": text}]
        )

        result_text = response.content[0].text
        # Extract JSON from response (sometimes Claude adds markdown blocks)
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            database.add_entry(
                user_id=update.effective_user.id,
                entry_type=data.get("type", "note"),
                raw_text=text,
                amount=data.get("amount"),
                currency=data.get("currency"),
                category=data.get("category"),
                content=data.get("content")
            )

            summary = f"✅ {LOCALIZED_MESSAGES[lang]['saved']}\n"
            if data.get("type") == "expense":
                summary += f"💰 {data.get('amount')} {data.get('currency')} ({data.get('category')})"
            else:
                summary += f"📝 {data.get('content')}"

            await msg.edit_text(summary)
        else:
            await msg.edit_text(LOCALIZED_MESSAGES[lang]["error"])

    except Exception as e:
        logging.error(f"Processing error: {e}")
        await msg.edit_text(f"{LOCALIZED_MESSAGES[lang]['error']}\n{str(e)[:100]}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_entry(update, context, update.message.text)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msg = await update.message.reply_text(LOCALIZED_MESSAGES[lang]["transcribing"])

    try:
        voice_file = await update.message.voice.get_file()
        file_path = f"voice_{update.effective_user.id}_{update.message.message_id}.ogg"
        await voice_file.download_to_drive(file_path)

        # Transcription lang code
        sr_lang = "uz-UZ"
        if lang == "lang_ru": sr_lang = "ru-RU"

        text = transcription.transcribe_audio(file_path, lang=sr_lang)
        os.remove(file_path)

        if text:
            await msg.edit_text(f"🎤: {text}")
            await process_entry(update, context, text)
        else:
            await msg.edit_text(LOCALIZED_MESSAGES[lang]["error"] + " (Transcription failed)")

    except Exception as e:
        logging.error(f"Voice error: {e}")
        await msg.edit_text(LOCALIZED_MESSAGES[lang]["error"])

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id
    data = database.get_today_summary(user_id)

    text = f"<b>{LOCALIZED_MESSAGES[lang]['summary_title']}</b>\n\n"

    if not data["expenses"] and not data["tasks"]:
        text += LOCALIZED_MESSAGES[lang]["no_data"]
    else:
        if data["expenses"]:
            text += f"{LOCALIZED_MESSAGES[lang]['expenses']}\n"
            for exp in data["expenses"]:
                text += f"- {exp[1]} {exp[2]}\n"

        if data["tasks"]:
            text += f"\n{LOCALIZED_MESSAGES[lang]['tasks']}\n"
            for task in data["tasks"]:
                text += f"- {task[0]}\n"

    await update.message.reply_text(text, parse_mode=constants.ParseMode.HTML)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id
    rows = database.get_recent_history(user_id)

    text = f"<b>{LOCALIZED_MESSAGES[lang]['history_title']}</b>\n\n"
    if not rows:
        text += LOCALIZED_MESSAGES[lang]["no_data"]
    else:
        for r in rows:
            icon = "💰" if r[0] == "expense" else "📝"
            val = f"{r[2]} {r[3]}" if r[2] else r[1][:30]
            text += f"{icon} {val} ({r[4][:16]})\n"

    await update.message.reply_text(text, parse_mode=constants.ParseMode.HTML)

def main():
    database.init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
