import os
import re
import json
import sqlite3
import datetime
import logging
import base64
import subprocess
import html
import imageio_ffmpeg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

TOKEN = os.environ.get("TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
DB_PATH = "records.db"

def get_anthropic_client():
    if not CLAUDE_API_KEY:
        return None
    return anthropic.Anthropic(api_key=CLAUDE_API_KEY)

L = {
    "lang_uz_cyr": {
        "start": "Илтимос, тилни танланг:",
        "lang_ok": "✅ Тил танланди!\n\nОвозли хабар юборинг (харажат, вазифа ёки эслатма). Мен уни таҳлил қилиб сақлаб қўяман.",
        "wait": "⏳ Илтимос, кутинг...",
        "ok": "✅ Сақланди!",
        "err": "❌ Хатолик юз берди.",
        "history_title": "📜 Сўнгги ёзувлар:",
        "history_empty": "Ҳозирча ёзувлар йўқ.",
        "expense": "Харажат",
        "task": "Вазифа",
        "note": "Эслатма",
        "bot": "🤖",
        "warn": "⚠️ Жавоблар AI томонидан яратилган."
    },
    "lang_uz_lat": {
        "start": "Iltimos, tilni tanlang:",
        "lang_ok": "✅ Til tanlandi!\n\nOvozli xabar yuboring (xarajat, vazifa yoki eslatma). Men uni tahlil qilib saqlab qo'yaman.",
        "wait": "⏳ Iltimos, kuting...",
        "ok": "✅ Saqlandi!",
        "err": "❌ Xatolik yuz berdi.",
        "history_title": "📜 So'nggi yozuvlar:",
        "history_empty": "Hozircha yozuvlar yo'q.",
        "expense": "Xarajat",
        "task": "Vazifa",
        "note": "Eslatma",
        "bot": "🤖",
        "warn": "⚠️ Javoblar AI tomonidan yaratilgan."
    },
    "lang_ru": {
        "start": "Пожалуйста, выберите язык:",
        "lang_ok": "✅ Язык выбран!\n\nОтправьте голосовое сообщение (расход, задача или заметка). Я проанализирую и сохраю его.",
        "wait": "⏳ Пожалуйста, подождите...",
        "ok": "✅ Сохранено!",
        "err": "❌ Произошла ошибка.",
        "history_title": "📜 Последние записи:",
        "history_empty": "Записей пока нет.",
        "expense": "Расход",
        "task": "Задача",
        "note": "Заметка",
        "bot": "🤖",
        "warn": "⚠️ Ответы созданы ИИ."
    }
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS records
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  timestamp DATETIME,
                  category TEXT,
                  content TEXT,
                  amount REAL)''')
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(
        L["lang_uz_cyr"]["start"],
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    await query.edit_message_text(L.get(lang, L["lang_uz_cyr"])["lang_ok"])

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L["lang_uz_cyr"])

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT category, content, amount, timestamp FROM records WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10",
              (update.effective_user.id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(texts["history_empty"])
        return

    res = [f"<b>{texts['history_title']}</b>\n"]
    for cat, cont, amo, ts in rows:
        cat_localized = texts.get(cat, cat)
        amount_str = f" ({amo})" if amo else ""
        # Format timestamp to readable string
        ts_dt = datetime.datetime.fromisoformat(ts) if isinstance(ts, str) else ts
        ts_str = ts_dt.strftime("%d.%m %H:%M")
        res.append(f"• {ts_str} | <b>{cat_localized}</b>: {html.escape(cont)}{amount_str}")

    await update.message.reply_text("\n".join(res), parse_mode=constants.ParseMode.HTML)

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
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)

    client = get_anthropic_client()
    if not client:
        await status_msg.edit_text("❌ CLAUDE_API_KEY missing.")
        return

    voice_file = await update.message.voice.get_file()
    ogg_path = f"v_{update.effective_chat.id}_{update.message.message_id}.ogg"
    mp3_path = ogg_path.replace(".ogg", ".mp3")

    try:
        await voice_file.download_to_drive(ogg_path)

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ffmpeg_exe, "-y", "-i", ogg_path, "-acodec", "libmp3lame", mp3_path],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(mp3_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode("utf-8")

        system_prompt = """Analyze the voice and return ONLY JSON with keys:
category (expense/task/note), content (string), amount (number or null).
Example: {"category": "expense", "content": "Lunch at KFC", "amount": 55000}"""

        response = client.beta.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "audio",
                        "source": {
                            "type": "base64",
                            "media_type": "audio/mpeg",
                            "data": audio_data
                        }
                    },
                    {
                        "type": "text",
                        "text": "Analyze this audio."
                    }
                ]
            }],
            extra_headers={"anthropic-beta": "audio-2024-10-31"}
        )

        res_text = response.content[0].text
        json_match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO records (user_id, timestamp, category, content, amount) VALUES (?, ?, ?, ?, ?)",
                      (update.effective_user.id, datetime.datetime.now(), data.get("category"), data.get("content"), data.get("amount")))
            conn.commit()
            conn.close()

            cat_localized = texts.get(data.get("category"), data.get("category"))
            amount_str = f" ({data.get('amount')})" if data.get("amount") else ""
            final_text = f"{texts['ok']}\n\n<b>{cat_localized}</b>: {data.get('content')}{amount_str}"
            await status_msg.edit_text(final_text, parse_mode=constants.ParseMode.HTML)
        else:
            await status_msg.edit_text(texts["err"])

    except Exception as e:
        print(f"VOICE ERROR: {e}")
        await status_msg.edit_text(texts["err"])
    finally:
        if os.path.exists(ogg_path): os.remove(ogg_path)
        if os.path.exists(mp3_path): os.remove(mp3_path)

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L["lang_uz_cyr"])
    question = update.message.text

    system = """Analyze the text and return ONLY JSON with keys:
category (expense/task/note), content (string), amount (number or null).
Example: {"category": "expense", "content": "Lunch at KFC", "amount": 55000}"""

    status_msg = await update.message.reply_text(texts["wait"])

    try:
        client = get_anthropic_client()
        if not client:
            await status_msg.edit_text("❌ CLAUDE_API_KEY missing.")
            return

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        res_text = message.content[0].text
        json_match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO records (user_id, timestamp, category, content, amount) VALUES (?, ?, ?, ?, ?)",
                      (update.effective_user.id, datetime.datetime.now(), data.get("category"), data.get("content"), data.get("amount")))
            conn.commit()
            conn.close()

            cat_localized = texts.get(data.get("category"), data.get("category"))
            amount_str = f" ({data.get('amount')})" if data.get("amount") else ""
            final_text = f"{texts['ok']}\n\n<b>{cat_localized}</b>: {data.get('content')}{amount_str}"
            await status_msg.edit_text(final_text, parse_mode=constants.ParseMode.HTML)
        else:
            await status_msg.edit_text(texts["err"])

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
