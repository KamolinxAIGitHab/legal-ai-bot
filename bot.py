import os
import re
import json
import sqlite3
import base64
from datetime import datetime

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
    "lang_uz_cyr": {"ok": "✅ Тил танланди!\n\nСаволингизни ёзинг ёки овозли хабар юборинг:", "wait": "⏳ Кутинг...", "warn": "⚠️ Таълимий мақсадда.", "err": "❌ Хато.", "api": "❌ API йўқ.", "auth": "❌ Калит хато.", "limit": "❌ Лимит.", "hist": "📊 Тарих:", "no_hist": "📭 Бўш.", "voice_ok": "✅ Сақланди!", "expense": "Харажат", "task": "Вазифа", "note": "Қайд"},
    "lang_uz_lat": {"ok": "✅ Til tanlandi!\n\nSavolingizni yozing yoki ovozli xabar yuboring:", "wait": "⏳ Kuting...", "warn": "⚠️ Ta'limiy maqsadda.", "err": "❌ Xato.", "api": "❌ API yo'q.", "auth": "❌ Kalit xato.", "limit": "❌ Limit.", "hist": "📊 Tarix:", "no_hist": "📭 Bo'sh.", "voice_ok": "✅ Saqlandi!", "expense": "Xarajat", "task": "Vazifa", "note": "Qayd"},
    "lang_ru": {"ok": "✅ Язык выбран!\n\nЗадайте вопрос или отправьте голосовое сообщение:", "wait": "⏳ Ждите...", "warn": "⚠️ В образовательных целях.", "err": "❌ Ошибка.", "api": "❌ Нет API.", "auth": "❌ Ошибка ключа.", "limit": "❌ Лимит.", "hist": "📊 История:", "no_hist": "📭 Пусто.", "voice_ok": "✅ Сохранено!", "expense": "Расход", "task": "Задача", "note": "Заметка"}
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

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    text = update.message.text
    status_msg = await update.message.reply_text(L[lang]["wait"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = "Analyze the text and return JSON with keys: category (expense/task/note), content, amount (number or null)."
        if lang == "lang_uz_cyr": prompt += " Respond in Uzbek Cyrillic."
        elif lang == "lang_uz_lat": prompt += " Respond in Uzbek Latin."

        msg = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            messages=[{"role": "user", "content": f"{prompt}\n\nText: {text}"}]
        )
        res_text = msg.content[0].text
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                conn = sqlite3.connect("records.db")
                cursor = conn.cursor()
                cursor.execute("INSERT INTO records (user_id, timestamp, category, content, amount) VALUES (?, ?, ?, ?, ?)",
                               (update.effective_user.id, datetime.now().isoformat(), data["category"], data["content"], data.get("amount")))
                conn.commit()
                conn.close()
                await status_msg.edit_text(f"{L[lang]['voice_ok']}\n\n{L[lang].get(data['category'], data['category'])}: {data['content']}")
            except (json.JSONDecodeError, KeyError) as e:
                await status_msg.edit_text(f"{L[lang]['err']} (JSON)")
        else:
            await status_msg.edit_text(L[lang]["err"])
    except Exception as e:
        await status_msg.edit_text(f"{L[lang]['err']} {str(e)[:100]}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    status_msg = await update.message.reply_text(L[lang]["wait"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    file = await context.bot.get_file(update.message.voice.file_id)
    file_path = f"voice_{update.effective_chat.id}_{update.message.message_id}.ogg"
    await file.download_to_drive(file_path)

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        with open(file_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode("utf-8")

        prompt = "Analyze the voice and return JSON with keys: category (expense/task/note), content, amount (number or null)."
        if lang == "lang_uz_cyr": prompt += " Respond in Uzbek Cyrillic."
        elif lang == "lang_uz_lat": prompt += " Respond in Uzbek Latin."

        msg = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            extra_headers={"anthropic-beta": "audio-2024-10-31"},
            messages=[{"role": "user", "content": [
                {"type": "audio", "source": {"type": "base64", "media_type": "audio/ogg", "data": audio_data}},
                {"type": "text", "text": prompt}
            ]}]
        )
        res_text = msg.content[0].text
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                conn = sqlite3.connect("records.db")
                cursor = conn.cursor()
                cursor.execute("INSERT INTO records (user_id, timestamp, category, content, amount) VALUES (?, ?, ?, ?, ?)",
                               (update.effective_user.id, datetime.now().isoformat(), data["category"], data["content"], data.get("amount")))
                conn.commit()
                conn.close()
                await status_msg.edit_text(f"{L[lang]['voice_ok']}\n\n{L[lang].get(data['category'], data['category'])}: {data['content']}")
            except (json.JSONDecodeError, KeyError):
                await status_msg.edit_text(f"{L[lang]['err']} (JSON)")
        else:
            await status_msg.edit_text(L[lang]["err"])
    except Exception as e:
        await status_msg.edit_text(f"{L[lang]['err']} {str(e)[:100]}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    conn = sqlite3.connect("records.db")
    cursor = conn.cursor()
    cursor.execute("SELECT category, content, amount FROM records WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (update.effective_user.id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(L[lang]["no_hist"])
        return

    text = f"{L[lang]['hist']}\n\n"
    for cat, cont, amt in rows:
        amt_str = f" ({amt})" if amt else ""
        text += f"• {L[lang].get(cat, cat)}: {cont}{amt_str}\n"
    await update.message.reply_text(text)

def init_db():
    conn = sqlite3.connect("records.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT,
            category TEXT,
            content TEXT,
            amount REAL
        )
    """)
    conn.commit()
    conn.close()

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
