import os
import re
import sqlite3
import base64
import json

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
        "ok": "✅ Тил танланди! Саволингизни ёзинг ёки овозли хабар юборинг:",
        "wait": "⏳ Жавоб тайёрланмоқда...",
        "err": "❌ Хатолик юз берди.",
        "hist": "🗂 Сўнгги ёзувлар:",
        "no_hist": "🗂 Ҳозирча ёзувлар йўқ.",
        "save": "💾 Сақланди: {cat}\n📝 {content}\n💰 {amount}"
    },
    "lang_uz_lat": {
        "ok": "✅ Til tanlandi! Savolingizni yozing yoki ovozli xabar yuboring:",
        "wait": "⏳ Javob tayyorlanmoqda...",
        "err": "❌ Xatolik yuz berdi.",
        "hist": "🗂 So'nggi yozuvlar:",
        "no_hist": "🗂 Hozircha yozuvlar yo'q.",
        "save": "💾 Saqlandi: {cat}\n📝 {content}\n💰 {amount}"
    },
    "lang_ru": {
        "ok": "✅ Язык выбран! Напишите вопрос или отправьте голосовое сообщение:",
        "wait": "⏳ Ответ готовится...",
        "err": "❌ Произошла ошибка.",
        "hist": "🗂 Последние записи:",
        "no_hist": "🗂 Записей пока нет.",
        "save": "💾 Сохранено: {cat}\n📝 {content}\n💰 {amount}"
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
    await query.edit_message_text(L[lang]["ok"])

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    text = update.message.text
    status_msg = await update.message.reply_text(L[lang]["wait"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        if not CLAUDE_API_KEY:
            await status_msg.edit_text("❌ CLAUDE_API_KEY missing.")
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = "Analyze the text and return JSON with keys: category (expense/task/note), content, amount (number or null)."

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=512,
            system=prompt,
            messages=[{"role": "user", "content": text}]
        )

        res_text = message.content[0].text
        match = re.search(r"\{.*\}", res_text, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(res_text)

        conn = sqlite3.connect("records.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO records (user_id, category, content, amount) VALUES (?, ?, ?, ?)",
            (update.effective_user.id, data["category"], data["content"], data["amount"])
        )
        conn.commit()
        conn.close()

        await status_msg.edit_text(L[lang]["save"].format(
            cat=data["category"], content=data["content"], amount=data["amount"] or "-"
        ))

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

    voice = update.message.voice
    voice_file = await context.bot.get_file(voice.file_id)
    file_path = f"voice_{update.effective_chat.id}_{update.message.message_id}.ogg"
    await voice_file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = "Analyze the voice and return JSON with keys: category (expense/task/note), content, amount (number or null)."

        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=512,
            system=prompt,
            extra_headers={"anthropic-beta": "audio-2024-10-31"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "audio", "source": {"type": "base64", "media_type": "audio/ogg", "data": audio_base64}},
                    {"type": "text", "text": "Analyze this audio."}
                ]
            }]
        )

        res_text = response.content[0].text
        match = re.search(r"\{.*\}", res_text, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(res_text)

        conn = sqlite3.connect("records.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO records (user_id, category, content, amount) VALUES (?, ?, ?, ?)",
            (update.effective_user.id, data["category"], data["content"], data["amount"])
        )
        conn.commit()
        conn.close()

        await status_msg.edit_text(L[lang]["save"].format(
            cat=data["category"], content=data["content"], amount=data["amount"] or "-"
        ))

    except Exception as e:
        print(f"VOICE ERROR: {e}")
        await status_msg.edit_text(L[lang]["err"])
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    conn = sqlite3.connect("records.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT category, content, amount FROM records WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10",
        (update.effective_user.id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(L[lang]["no_hist"])
        return

    text = f"{L[lang]['hist']}\n\n"
    for r in rows:
        text += f"• {r[0].capitalize()}: {r[1]} ({r[2] or '-'})\n"

    await update.message.reply_text(text)

def main():
    # Initialize DB
    conn = sqlite3.connect("records.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            category TEXT,
            content TEXT,
            amount REAL
        )
    ''')
    conn.commit()
    conn.close()

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
