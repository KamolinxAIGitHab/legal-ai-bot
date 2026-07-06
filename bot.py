import os
import re
import sqlite3
import json
import subprocess
import base64
import html

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic
import imageio_ffmpeg

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

L = {
    "lang_uz_cyr": {
        "start": "✅ Тил танланди!\n\nОвозли ёки матнли хабар юборинг. Мен уни категорияларга (харажат, иш, қайд) ажратиб сақлайман.",
        "wait": "⏳ Илтимос, кутинг...",
        "ok": "✅ Сақланди!",
        "err": "❌ Хатолик юз берди.",
        "warn": "⚠️ Жавоблар AI томонидан яратилган.",
        "history": "📊 Охирги 10 та қайд:",
        "no_history": "📭 Қайдлар топилмади.",
        "cat_expense": "Харажат",
        "cat_task": "Иш",
        "cat_note": "Қайд",
        "bot": "🤖"
    },
    "lang_uz_lat": {
        "start": "✅ Til tanlandi!\n\nOvozli yoki matnli xabar yuboring. Men uni kategoriyalarga (xarajat, ish, qayd) ajratib saqlayman.",
        "wait": "⏳ Iltimos, kuting...",
        "ok": "✅ Saqlandi!",
        "err": "❌ Xatolik yuz berdi.",
        "warn": "⚠️ Javoblar AI tomonidan yaratilgan.",
        "history": "📊 Oxirgi 10 ta qayd:",
        "no_history": "📭 Qaydlar topilmadi.",
        "cat_expense": "Xarajat",
        "cat_task": "Ish",
        "cat_note": "Qayd",
        "bot": "🤖"
    },
    "lang_ru": {
        "start": "✅ Язык выбран!\n\nОтправьте голосовое или текстовое сообщение. Я распределю его по категориям (расход, задача, заметка) и сохраню.",
        "wait": "⏳ Пожалуйста, подождите...",
        "ok": "✅ Сохранено!",
        "err": "❌ Произошла ошибка.",
        "warn": "⚠️ Ответы созданы AI.",
        "history": "📊 Последние 10 записей:",
        "no_history": "📭 Записей не найдено.",
        "cat_expense": "Расход",
        "cat_task": "Задача",
        "cat_note": "Заметка",
        "bot": "🤖"
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
    await update.message.reply_text(
        "Илтимос, тилни танланг:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    texts = L.get(lang, L["lang_uz_cyr"])
    await query.edit_message_text(texts["start"])

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L["lang_uz_cyr"])

    status_msg = await update.message.reply_text(texts["wait"])

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    ogg_path = f"v_{update.message.chat_id}_{update.message.message_id}.ogg"
    mp3_path = ogg_path.replace(".ogg", ".mp3")

    try:
        await file.download_to_drive(ogg_path)
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ffmpeg_exe, "-y", "-i", ogg_path, mp3_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(mp3_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        system_prompt = "Analyze the audio and return ONLY JSON with keys: category (expense/task/note), content, amount (number or null). Categories must be one of: expense, task, note."

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            extra_headers={"anthropic-beta": "audio-2024-10-31"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "audio",
                            "source": {
                                "type": "base64",
                                "media_type": "audio/mpeg",
                                "data": audio_base64
                            }
                        },
                        {"type": "text", "text": "Analyze this note."}
                    ]
                }
            ]
        )

        res_text = message.content[0].text
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            conn = sqlite3.connect("records.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO records (user_id, category, content, amount) VALUES (?, ?, ?, ?)",
                           (update.effective_user.id, data.get("category"), data.get("content"), data.get("amount")))
            conn.commit()
            conn.close()

            cat_name = texts.get(f"cat_{data.get('category')}", data.get("category"))
            res_display = f"✅ {cat_name}: {data.get('content')}"
            if data.get("amount"):
                res_display += f"\n💰 {data.get('amount')}"

            await status_msg.edit_text(f"{texts['bot']} {res_display}\n\n{texts['ok']}")
        else:
            await status_msg.edit_text(texts["err"])

    except Exception as e:
        print(f"VOICE ERROR: {e}")
        await status_msg.edit_text(texts["err"])
    finally:
        if os.path.exists(ogg_path): os.remove(ogg_path)
        if os.path.exists(mp3_path): os.remove(mp3_path)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L["lang_uz_cyr"])

    conn = sqlite3.connect("records.db")
    cursor = conn.cursor()
    cursor.execute("SELECT category, content, amount, timestamp FROM records WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (update.effective_user.id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(texts["no_history"])
        return

    res = f"<b>{texts['history']}</b>\n\n"
    for row in rows:
        cat_name = texts.get(f"cat_{row[0]}", row[0])
        content = html.escape(row[1])
        amount = row[2]
        time = row[3]

        line = f"📅 {time}\n🏷 {cat_name}: {content}"
        if amount:
            line += f" | 💰 {amount}"
        res += line + "\n\n"

    await update.message.reply_text(res, parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L["lang_uz_cyr"])
    question = update.message.text

    status_msg = await update.message.reply_text(texts["wait"])

    try:
        if not CLAUDE_API_KEY:
            await status_msg.edit_text("❌ CLAUDE_API_KEY missing.")
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        system = "Analyze the text and return ONLY JSON with keys: category (expense/task/note), content, amount (number or null). Categories: expense, task, note."

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )

        res_text = message.content[0].text
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            conn = sqlite3.connect("records.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO records (user_id, category, content, amount) VALUES (?, ?, ?, ?)",
                           (update.effective_user.id, data.get("category"), data.get("content"), data.get("amount")))
            conn.commit()
            conn.close()

            cat_name = texts.get(f"cat_{data.get('category')}", data.get("category"))
            res_display = f"✅ {cat_name}: {data.get('content')}"
            if data.get("amount"):
                res_display += f"\n💰 {data.get('amount')}"

            await status_msg.edit_text(f"{texts['bot']} {res_display}\n\n{texts['ok']}")
        else:
            await status_msg.edit_text(texts["err"])

    except Exception as e:
        print(f"TEXT ERROR: {e}")
        await status_msg.edit_text(texts["err"])

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
