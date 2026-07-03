import os
import re
import json
import sqlite3
import base64
import subprocess
import html
import imageio_ffmpeg
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
        "start": "Илтимос, тилни танланг:",
        "selected": "✅ Тил танланди!\n\nОвозли хабар юборинг (харажат, вазифа ёки қайд) ёки савол ёзинг:",
        "wait": "⏳ Илтимос, кутиб туринг...",
        "ok": "✅ Сақланди!",
        "history_title": "📊 Охирги 10 та ёзув:",
        "no_history": "📭 Ҳозирча ёзувлар йўқ.",
        "err": "❌ Хатолик юз берди.",
        "api": "❌ API калит топилмади.",
        "expense": "Харажат", "task": "Вазифа", "note": "Қайд"
    },
    "lang_uz_lat": {
        "start": "Iltimos, tilni tanlang:",
        "selected": "✅ Til tanlandi!\n\nOvozli xabar yuboring (xarajat, vazifa yoki qayd) yoki savol yozing:",
        "wait": "⏳ Iltimos, kutib turing...",
        "ok": "✅ Saqlandi!",
        "history_title": "📊 Oxirgi 10 ta yozuv:",
        "no_history": "📭 Hozircha yozuvlar yo'q.",
        "err": "❌ Xatolik yuz berdi.",
        "api": "❌ API kalit topilmadi.",
        "expense": "Xarajat", "task": "Vazifa", "note": "Qayd"
    },
    "lang_ru": {
        "start": "Пожалуйста, выберите язык:",
        "selected": "✅ Язык выбран!\n\nОтправьте голосовое сообщение (расход, задача или заметка) или напишите вопрос:",
        "wait": "⏳ Пожалуйста, подождите...",
        "ok": "✅ Сохранено!",
        "history_title": "📊 Последние 10 записей:",
        "no_history": "📭 Записей пока нет.",
        "err": "❌ Произошла ошибка.",
        "api": "❌ API ключ не найден.",
        "expense": "Расход", "task": "Задача", "note": "Заметка"
    }
}

def init_db():
    conn = sqlite3.connect("records.db")
    curr = conn.cursor()
    curr.execute("""
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
    await update.message.reply_text(L["lang_uz_cyr"]["start"], reply_markup=InlineKeyboardMarkup(keyboard))

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    await query.edit_message_text(L.get(lang, L["lang_uz_cyr"])["selected"])

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L["lang_uz_cyr"])

    if not CLAUDE_API_KEY:
        await update.message.reply_text(texts["api"])
        return

    status_msg = await update.message.reply_text(texts["wait"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    voice_file = await update.message.voice.get_file()
    temp_ogg = f"voice_{update.effective_user.id}_{update.message.message_id}.ogg"
    temp_wav = temp_ogg.replace(".ogg", ".wav")

    try:
        await voice_file.download_to_drive(temp_ogg)
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ffmpeg_exe, "-i", temp_ogg, temp_wav, "-y", "-loglevel", "quiet"], check=True)

        with open(temp_wav, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        sys_prompt = "Analyze the voice and return JSON with keys: category (expense/task/note), content, amount (number or null)."

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            extra_headers={"anthropic-beta": "audio-2024-10-31"},
            system=sys_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "audio", "source": {"type": "base64", "media_type": "audio/wav", "data": audio_data}},
                    {"type": "text", "text": "Process this voice recording."}
                ]
            }]
        )

        res_text = message.content[0].text
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            conn = sqlite3.connect("records.db")
            curr = conn.cursor()
            curr.execute(
                "INSERT INTO records (user_id, category, content, amount) VALUES (?, ?, ?, ?)",
                (update.effective_user.id, data['category'], data['content'], data.get('amount'))
            )
            conn.commit()
            conn.close()

            cat_label = texts.get(data['category'], data['category'])
            amt_str = f" ({data['amount']})" if data.get('amount') else ""
            await status_msg.edit_text(f"✅ {cat_label}: {data['content']}{amt_str}")
        else:
            await status_msg.edit_text(res_text)

    except Exception as e:
        await status_msg.edit_text(f"{texts['err']}\n{str(e)[:100]}")
    finally:
        for f in [temp_ogg, temp_wav]:
            if os.path.exists(f): os.remove(f)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L["lang_uz_cyr"])

    conn = sqlite3.connect("records.db")
    curr = conn.cursor()
    curr.execute("SELECT category, content, amount, timestamp FROM records WHERE user_id = ? ORDER BY id DESC LIMIT 10", (update.effective_user.id,))
    rows = curr.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(texts["no_history"])
        return

    res = [f"<b>{texts['history_title']}</b>\n"]
    for cat, content, amt, ts in rows:
        cat_label = texts.get(cat, cat)
        amt_str = f" - {amt}" if amt else ""
        escaped_content = html.escape(content)
        res.append(f"• {ts[:16]} | {cat_label}: {escaped_content}{amt_str}")

    await update.message.reply_text("\n".join(res), parse_mode="HTML")

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L["lang_uz_cyr"])
    question = update.message.text

    await update.message.reply_text(texts["wait"])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        if not CLAUDE_API_KEY:
            await update.message.reply_text(texts["api"])
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": question}]
        )
        await update.message.reply_text(f"🤖 {message.content[0].text}")
    except Exception as e:
        await update.message.reply_text(f"{texts['err']}\n{str(e)[:100]}")

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
