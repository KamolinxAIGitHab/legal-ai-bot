import os
import re
import sqlite3
import base64
import json
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from telegram.constants import ChatAction
import anthropic

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

L = {
    "lang_uz_cyr": {
        "ok": "✅ Бажарилди!", "wait": "⏳ Илтимос, кутинг...",
        "err": "❌ Хатолик юз берди.", "hist": "📊 Охирги 10 та қайд:",
        "no_hist": "📭 Қайдлар топилмади.", "warn": "⚠️ Маълумотлар AI томонидан таҳлил қилинди."
    },
    "lang_uz_lat": {
        "ok": "✅ Bajarildi!", "wait": "⏳ Iltimos, kuting...",
        "err": "❌ Xatolik yuz berdi.", "hist": "📊 Oxirgi 10 ta qayd:",
        "no_hist": "📭 Qaydlar topilmadi.", "warn": "⚠️ Ma'lumotlar AI tomonidan tahlil qilindi."
    },
    "lang_ru": {
        "ok": "✅ Готово!", "wait": "⏳ Пожалуйста, подождите...",
        "err": "❌ Произошла ошибка.", "hist": "📊 Последние 10 записей:",
        "no_hist": "📭 Записей не найдено.", "warn": "⚠️ Данные проанализированы AI."
    }
}

def init_db():
    conn = sqlite3.connect("records.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            category TEXT,
            content TEXT,
            amount REAL
        )
    """)
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    msg = (
        "🇺🇿 Илтимос, тилни танланг / Iltimos, tilni tanlang\n"
        "🇷🇺 Пожалуйста, выберите язык:"
    )
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang

    welcome = {
        "lang_uz_cyr": "✅ Тил танланди!\n\nОвозли хабар юборинг (харажат, вазифа ёки қайд) ёки ҳуқуқий савол беринг. Тарих учун /history буйруғидан фойдаланинг.",
        "lang_uz_lat": "✅ Til tanlandi!\n\nOvozli xabar yuboring (xarajat, vazifa yoki qayd) yoki huquqiy savol bering. Tarix uchun /history buyrug'idan foydalaning.",
        "lang_ru": "✅ Язык выбран!\n\nОтправьте голосовое сообщение (расход, задача или заметка) или задайте юридический вопрос. Для истории используйте /history."
    }
    await query.edit_message_text(welcome.get(lang, welcome["lang_uz_cyr"]))

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    user_id = update.effective_user.id

    conn = sqlite3.connect("records.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, category, content, amount FROM records WHERE user_id=? ORDER BY timestamp DESC LIMIT 10",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(L[lang]["no_hist"])
        return

    text = f"{L[lang]['hist']}\n\n"
    for ts, cat, content, amt in rows:
        icon = {"expense": "💸", "task": "✅", "note": "📝"}.get(cat, "📌")
        amt_str = f" ({amt})" if amt else ""
        text += f"{ts} | {icon} {content}{amt_str}\n"

    await update.message.reply_text(text)

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
    voice = update.message.voice
    user_id = update.effective_user.id

    status_msg = await update.message.reply_text(L[lang]["wait"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        file = await context.bot.get_file(voice.file_id)
        file_path = f"voice_{user_id}_{update.message.message_id}.ogg"
        await file.download_to_drive(file_path)

        with open(file_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode("utf-8")

        Path(file_path).unlink() # Cleanup

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

        prompt = {
            "lang_uz_cyr": "Овозни таҳлил қилинг ва JSON қайтаринг: category (expense/task/note), content, amount (рақам ёки null).",
            "lang_uz_lat": "Ovozni tahlil qiling va JSON qaytaring: category (expense/task/note), content, amount (raqam yoki null).",
            "lang_ru": "Проанализируйте голос и верните JSON: category (expense/task/note), content, amount (число или null)."
        }.get(lang)

        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            extra_headers={"anthropic-beta": "audio-2024-10-31"},
            system=prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "audio", "source": {"type": "base64", "media_type": "audio/ogg", "data": audio_base64}}
                    ]
                }
            ]
        )

        res_text = response.content[0].text
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            data = json.loads(match.group())

            conn = sqlite3.connect("records.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO records (user_id, category, content, amount) VALUES (?, ?, ?, ?)",
                (user_id, data.get("category"), data.get("content"), data.get("amount"))
            )
            conn.commit()
            conn.close()

            icon = {"expense": "💸", "task": "✅", "note": "📝"}.get(data.get("category"), "📌")
            amt_str = f" ({data.get('amount')})" if data.get("amount") else ""
            final_text = f"{L[lang]['ok']}\n\n{icon} {data.get('content')}{amt_str}\n\n{L[lang]['warn']}"
            await status_msg.edit_text(final_text)
        else:
            await status_msg.edit_text(L[lang]["err"])

    except Exception as e:
        print(f"VOICE XATO: {e}")
        await status_msg.edit_text(f"{L[lang]['err']}\n{str(e)[:100]}")

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
