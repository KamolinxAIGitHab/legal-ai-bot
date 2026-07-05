import os
import re
import sqlite3
import json
import base64
import subprocess
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

def init_db():
    conn = sqlite3.connect("records.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        category TEXT, content TEXT, amount REAL)""")
    conn.commit()
    conn.close()

L = {
    'lang_uz_cyr': {
        'start': "Ассалому алайкум! Овозли хабар юборинг (харажат, вазифа ёки қайд), мен уни сақлаб қўяман.",
        'wait': "⏳ Илтимос, кутиб туринг...", 'ok': "✅ Сақланди!", 'err': "❌ Хатолик.",
        'history': "📜 Охирги 10 та қайд:", 'empty': "📭 Қайдлар йўқ.",
        'bot': "🤖 Жавоб:", 'warn': "⚠️ Sonnet 3.5"
    },
    'lang_uz_lat': {
        'start': "Assalomu alaykum! Ovozli xabar yuboring (xarajat, vazifa yoki qayd), men uni saqlab qo'yaman.",
        'wait': "⏳ Iltimos, kutib turing...", 'ok': "✅ Saqlandi!", 'err': "❌ Xatolik.",
        'history': "📜 Oxirgi 10 ta qayd:", 'empty': "📭 Qaydlar yo'q.",
        'bot': "🤖 Javob:", 'warn': "⚠️ Sonnet 3.5"
    },
    'lang_ru': {
        'start': "Здравствуйте! Отправьте голосовое сообщение, и я сохраню его.",
        'wait': "⏳ Подождите...", 'ok': "✅ Сохранено!", 'err': "❌ Ошибка.",
        'history': "📜 Последние 10 записей:", 'empty': "📭 Записей нет.",
        'bot': "🤖 Ответ:", 'warn': "⚠️ Sonnet 3.5"
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
    texts = L.get(lang, L['lang_uz_cyr'])
    await query.edit_message_text(f"✅ {texts['start']}")

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L['lang_uz_cyr'])
    status_msg = await update.message.reply_text(texts['wait'])
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    voice_file = await update.message.voice.get_file()
    ogg_path = f"v_{update.effective_chat.id}_{update.message.message_id}.ogg"
    mp3_path = ogg_path.replace(".ogg", ".mp3")

    try:
        await voice_file.download_to_drive(ogg_path)
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ffmpeg_exe, "-y", "-i", ogg_path, mp3_path], check=True, capture_output=True)

        with open(mp3_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = "Analyze the voice and return JSON with keys: category (expense/task/note), content, amount (number or null)."

        res = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            extra_headers={"anthropic-beta": "audio-2024-10-31"},
            system=f"Language: {lang}. Output JSON only.",
            messages=[{"role": "user", "content": [
                {"type": "audio", "source": {"type": "base64", "media_type": "audio/mpeg", "data": audio_base64}},
                {"type": "text", "text": prompt}
            ]}]
        )

        res_text = res.content[0].text
        data = json.loads(re.search(r'\{.*\}', res_text, re.DOTALL).group())

        conn = sqlite3.connect("records.db")
        conn.execute("INSERT INTO records (user_id, category, content, amount) VALUES (?,?,?,?)",
                     (update.effective_user.id, data['category'], data['content'], data['amount']))
        conn.commit()
        conn.close()

        summary = f"{texts['ok']}\n📦 {data['category']}: {data['content']}"
        if data['amount']: summary += f" | 💰 {data['amount']}"
        await status_msg.edit_text(summary)

    except Exception as e:
        print(f"VOICE ERROR: {e}")
        await status_msg.edit_text(texts['err'])
    finally:
        for p in [ogg_path, mp3_path]:
            if os.path.exists(p): os.remove(p)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L['lang_uz_cyr'])
    conn = sqlite3.connect("records.db")
    rows = conn.execute("SELECT category, content, amount FROM records WHERE user_id=? ORDER BY id DESC LIMIT 10",
                        (update.effective_user.id,)).fetchall()
    conn.close()
    if not rows: return await update.message.reply_text(texts['empty'])
    res = f"{texts['history']}\n" + "\n".join([f"- {r[0]}: {r[1]} {f'({r[2]})' if r[2] else ''}" for r in rows])
    await update.message.reply_text(res)

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L['lang_uz_cyr'])
    question = update.message.text
    system = f"You are a helpful assistant. User language: {lang}. Be concise."
    status_msg = await update.message.reply_text(texts['wait'])

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024, system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)
        await status_msg.edit_text(f"{texts['bot']} {answer}\n\n{texts['warn']}")

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
