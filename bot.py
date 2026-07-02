import os
import re
import sqlite3
import base64
import json
import subprocess
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic
import imageio_ffmpeg

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
    context.user_data["lang"] = query.data
    L = {
        "lang_uz_cyr": "✅ Тил танланди!\n\nОвозли хабар юборинг (харажат, вазифа ёки қайд) ёки саволингизни ёзинг:",
        "lang_uz_lat": "✅ Til tanlandi!\n\nOvozli xabar yuboring (xarajat, vazifa yoki qayd) yoki savolingizni yozing:",
        "lang_ru": "✅ Язык выбран!\n\nОтправьте голосовое сообщение (расход, задача или заметка) или напишите свой вопрос:",
    }
    await query.edit_message_text(L.get(query.data, L["lang_uz_cyr"]))

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

    L = {
        "lang_uz_cyr": {"wait": "⏳ Жавоб тайёрланмоқда...", "api": "❌ API калит топилмади.", "auth": "❌ API калит нотўғри.", "limit": "❌ API лимити тугади."},
        "lang_uz_lat": {"wait": "⏳ Javob tayyorlanmoqda...", "api": "❌ API kalit topilmadi.", "auth": "❌ API kalit noto'g'ri.", "limit": "❌ API limiti tugadi."},
        "lang_ru": {"wait": "⏳ Ответ готовится...", "api": "❌ API ключ не найден.", "auth": "❌ Неверный API ключ.", "limit": "❌ Лимит API исчерпан."},
    }
    msg = L.get(lang, L["lang_uz_cyr"])

    if lang == "lang_uz_cyr":
        system = """Сиз шахсий ёрдамчисиз. Фойдаланувчига харажатларини, вазифаларини ва қайдларини бошқаришда ёрдам берасиз.
Қоидалар:
1. Фақат ўзбек тилида, кирилл алифбосида ёзинг
2. Қисқа ва аниқ жавоб беринг
3. Markdown ишлатманг"""

    elif lang == "lang_uz_lat":
        system = """Siz shaxsiy yordamchisiz. Foydalanuvchiga xarajatlarini, vazifalarini va qaydlarini boshqarishda yordam berasiz.
Qoidalar:
1. O'zbek tilida lotin alifbosida javob bering
2. Qisqa va aniq javob bering
3. Markdown ishlatmang"""

    else:
        system = """Вы личный помощник. Помогаете пользователю управлять расходами, задачами и заметками.
Правила:
1. Отвечайте на русском языке
2. Пишите кратко и по делу
3. Не используйте Markdown"""

    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    status = await update.message.reply_text(msg["wait"])

    try:
        if not CLAUDE_API_KEY:
            await status.edit_text(msg["api"])
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)
        await status.edit_text(f"🤖 {answer}\n\n⚠️ Жавоблар умумий ва таълимий мақсадда.")

    except anthropic.AuthenticationError:
        await status.edit_text(msg["auth"])
    except anthropic.RateLimitError:
        await status.edit_text(msg["limit"])
    except Exception as e:
        print(f"XATO TURI: {type(e).__name__}")
        print(f"XATO MATNI: {e}")
        await update.message.reply_text(
            f"❌ Хато: {type(e).__name__}: {str(e)[:200]}"
        )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    L = {
        "lang_uz_cyr": {"title": "📜 Сўнгги ёзувлар:", "empty": "Ҳозирча ёзувлар йўқ."},
        "lang_uz_lat": {"title": "📜 So'nggi yozuvlar:", "empty": "Hozircha yozuvlar yo'q."},
        "lang_ru": {"title": "📜 Последние записи:", "empty": "Записей пока нет."},
    }
    msg = L.get(lang, L["lang_uz_cyr"])

    conn = sqlite3.connect("records.db")
    cursor = conn.cursor()
    cursor.execute("SELECT category, content, amount, timestamp FROM records WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (update.effective_user.id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(msg["empty"])
        return

    text = f"{msg['title']}\n\n"
    for cat, content, amount, ts in rows:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f").strftime("%d.%m %H:%M")
        text += f"🔹 {dt} | {cat}: {content}" + (f" ({amount})" if amount else "") + "\n"

    await update.message.reply_text(text)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    L = {
        "lang_uz_cyr": {"wait": "🎙 Эшитяпман...", "ok": "✅ Сақланди!", "err": "❌ Хатолик юз берди"},
        "lang_uz_lat": {"wait": "🎙 Eshityapman...", "ok": "✅ Saqlandi!", "err": "❌ Xatolik yuz berdi"},
        "lang_ru": {"wait": "🎙 Слушаю...", "ok": "✅ Сохранено!", "err": "❌ Произошла ошибка"},
    }
    msg = L.get(lang, L["lang_uz_cyr"])
    status = await update.message.reply_text(msg["wait"])

    voice = await context.bot.get_file(update.message.voice.file_id)
    ogg_path = f"v_{update.message.chat_id}_{update.message.message_id}.ogg"
    wav_path = ogg_path.replace(".ogg", ".wav")

    try:
        await voice.download_to_drive(ogg_path)
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ffmpeg_exe, "-y", "-i", ogg_path, "-ar", "16000", wav_path], check=True, capture_output=True)

        with open(wav_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = "Analyze voice. Return JSON: {category: expense/task/note, content, amount: number/null}"
        res = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            system=prompt,
            extra_headers={"anthropic-beta": "audio-2024-10-31"},
            messages=[{"role": "user", "content": [{"type": "audio", "source": {"type": "base64", "media_type": "audio/wav", "data": audio_data}}]}]
        )

        data = json.loads(re.search(r"\{.*\}", res.content[0].text, re.DOTALL).group())
        conn = sqlite3.connect("records.db")
        conn.execute("INSERT INTO records (user_id, timestamp, category, content, amount) VALUES (?, ?, ?, ?, ?)",
                     (update.effective_user.id, datetime.now(), data["category"], data["content"], data.get("amount")))
        conn.commit()
        conn.close()

        await status.edit_text(f"{msg['ok']}\n\n📂 {data['category']}: {data['content']}" + (f" ({data['amount']})" if data.get("amount") else ""))

    except Exception as e:
        await status.edit_text(f"{msg['err']}: {str(e)}")
    finally:
        for p in [ogg_path, wav_path]:
            if os.path.exists(p): os.remove(p)

def init_db():
    conn = sqlite3.connect("records.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp DATETIME,
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
