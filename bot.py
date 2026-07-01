import os
import re
import sqlite3
import json
import base64
import logging
import subprocess

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

L = {
    "lang_uz_cyr": {
        "ok": "✅ Сақланди!", "wait": "⏳ Ишлаяпман...", "err": "❌ Хатолик юз берди.",
        "api": "❌ API калит топилмади.", "auth": "❌ API калит нотўғри.", "limit": "❌ Лимит тугади.",
        "hist": "📜 Охирги 10 та қайднома:", "no_hist": "🗂 Қайдномалар мавжуд эмас.",
        "welcome": "Ассалому алайкум! Мен сизнинг шахсий ёрдамчингизман. Харажатлар, вазифалар ёки қайдларни овозли ёки матн кўринишида юборинг.",
        "chosen": "✅ Тил танланди! Энди хабар юборишингиз мумкин."
    },
    "lang_uz_lat": {
        "ok": "✅ Saqlandi!", "wait": "⏳ Ishlayapman...", "err": "❌ Xatolik yuz berdi.",
        "api": "❌ API kalit topilmadi.", "auth": "❌ API kalit noto'g'ri.", "limit": "❌ Limit tugadi.",
        "hist": "📜 Oxirgi 10 ta qaydnoma:", "no_hist": "🗂 Qaydnomalar mavjud emas.",
        "welcome": "Assalomu alaykum! Men sizning shaxsiy yordamchingizman. Xarajatlar, vazifalar yoki qaydlarni ovozli yoki matn ko'rinishida yuboring.",
        "chosen": "✅ Til tanlandi! Endi xabar yuborishingiz mumkin."
    },
    "lang_ru": {
        "ok": "✅ Сохранено!", "wait": "⏳ Обрабатываю...", "err": "❌ Произошла ошибка.",
        "api": "❌ API ключ не найден.", "auth": "❌ Неверный API ключ.", "limit": "❌ Лимит исчерпан.",
        "hist": "📜 Последние 10 записей:", "no_hist": "🗂 Записи отсутствуют.",
        "welcome": "Здравствуйте! Я ваш личный помощник. Отправляйте расходы, задачи или заметки голосом или текстом.",
        "chosen": "✅ Язык выбран! Теперь вы можете отправлять сообщения."
    }
}

def init_db():
    conn = sqlite3.connect("records.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        category TEXT, content TEXT, amount REAL
    )""")
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
          [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
          [InlineKeyboardButton("Русский", callback_data="lang_ru")]]
    await update.message.reply_text("Тилни танланг / Tilni tanlang / Выберите язык:",
                                   reply_markup=InlineKeyboardMarkup(kb))

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = q.data
    context.user_data["lang"] = lang
    await q.edit_message_text(f"{L[lang]['chosen']}\n\n{L[lang]['welcome']}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    status_msg = await update.message.reply_text(L[lang]["wait"])
    path = f"v_{update.effective_user.id}_{update.message.message_id}.ogg"
    wav_path = path.replace(".ogg", ".wav")
    try:
        f = await context.bot.get_file(update.message.voice.file_id)
        await f.download_to_drive(path)
        subprocess.run(["ffmpeg", "-i", path, wav_path, "-y"], check=True)
        with open(wav_path, "rb") as audio_f:
            audio_b64 = base64.b64encode(audio_f.read()).decode("utf-8")
        res = client.messages.create(
            model="claude-3-5-sonnet-20241022", max_tokens=500,
            extra_headers={"anthropic-beta": "audio-2024-10-31"},
            system="Return JSON: {category: expense/task/note, content, amount: number/null}.",
            messages=[{"role": "user", "content": [
                {"type": "audio", "source": {"type": "base64", "media_type": "audio/wav", "data": audio_b64}},
                {"type": "text", "text": "Analyze memo."}
            ]}]
        )
        m = re.search(r"\{.*\}", res.content[0].text, re.DOTALL)
        d = json.loads(m.group()) if m else {}
        if d.get("category"):
            conn = sqlite3.connect("records.db")
            conn.execute("INSERT INTO records (user_id, category, content, amount) VALUES (?, ?, ?, ?)",
                         (update.effective_user.id, d["category"], d["content"], d.get("amount")))
            conn.commit(); conn.close()
            await status_msg.edit_text(f"{L[lang]['ok']}\n\n{d['category'].capitalize()}: {d['content']}")
        else: await status_msg.edit_text(L[lang]["err"])
    except Exception as e:
        logging.error(f"Voice error: {e}")
        await status_msg.edit_text(L[lang]["err"])
    finally:
        for p in [path, wav_path]:
            if os.path.exists(p): os.remove(p)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    try:
        conn = sqlite3.connect("records.db")
        rows = conn.execute("SELECT category, content, amount, timestamp FROM records WHERE user_id = ? ORDER BY id DESC LIMIT 10",
                            (update.effective_user.id,)).fetchall()
        conn.close()
        if not rows: return await update.message.reply_text(L[lang]["no_hist"])
        msg = L[lang]["hist"] + "\n\n"
        for r in rows:
            amt = f" ({r[2]})" if r[2] else ""
            msg += f"🔹 {r[3][:16]} | {r[0].capitalize()}: {r[1]}{amt}\n"
        await update.message.reply_text(msg)
    except Exception as e:
        logging.error(f"History error: {e}")
        await update.message.reply_text(L[lang]["err"])

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    status_msg = await update.message.reply_text(L[lang]["wait"])
    try:
        res = client.messages.create(
            model="claude-3-5-sonnet-20241022", max_tokens=500,
            system="Return JSON: {category: expense/task/note, content, amount: number/null}.",
            messages=[{"role": "user", "content": update.message.text}]
        )
        m = re.search(r"\{.*\}", res.content[0].text, re.DOTALL)
        d = json.loads(m.group()) if m else {}
        if d.get("category"):
            conn = sqlite3.connect("records.db")
            conn.execute("INSERT INTO records (user_id, category, content, amount) VALUES (?, ?, ?, ?)",
                         (update.effective_user.id, d["category"], d["content"], d.get("amount")))
            conn.commit(); conn.close()
            await status_msg.edit_text(f"{L[lang]['ok']}\n\n{d['category'].capitalize()}: {d['content']}")
        else: await status_msg.edit_text(L[lang]["err"])
    except Exception as e:
        logging.error(f"Text error: {e}")
        await status_msg.edit_text(L[lang]["err"])

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
