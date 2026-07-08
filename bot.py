import os
import re
import json
import sqlite3
import base64
import subprocess
import html
import logging
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
DB_PATH = os.environ.get("DB_PATH", "records.db")
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

L = {
    'lang_uz_cyr': {
        'start': "Тилни танланг / Пожалуйста, выберите язык:",
        'chosen': "✅ Тил танланди! Энди овозли хабар ёки матн юборишингиз мумкин. Мен уларни тоифаларга ажратиб сақлаб қўяман.",
        'wait': "⏳ Илтимос, кутинг...",
        'ok': "✅ Сақланди!",
        'err': "❌ Хатолик юз берди.",
        'err_auth': "❌ API калит билан муаммо.",
        'err_limit': "❌ Лимит тугади.",
        'history_title': "📜 Сўнгги 10 та қайд:",
        'empty': "📭 Ҳозирча қайдлар йўқ.",
        'category': "Тур",
        'content': "Мазмун",
        'amount': "Сумма",
        'expense': "Харажат",
        'task': "Вазифа",
        'note': "Қайд"
    },
    'lang_uz_lat': {
        'start': "Tilni tanlang / Пожалуйста, выберите язык:",
        'chosen': "✅ Til tanlandi! Endi ovozli xabar yoki matn yuborishingiz mumkin. Men ularni toifalarga ajratib saqlab qo'yaman.",
        'wait': "⏳ Iltimos, kuting...",
        'ok': "✅ Saqlandi!",
        'err': "❌ Xatolik yuz berdi.",
        'err_auth': "❌ API kalit bilan muammo.",
        'err_limit': "❌ Limit tugadi.",
        'history_title': "📜 So'nggi 10 ta qayd:",
        'empty': "📭 Hozircha qaydlar yo'q.",
        'category': "Tur",
        'content': "Mazmun",
        'amount': "Summa",
        'expense': "Xarajat",
        'task': "Vazifa",
        'note': "Qayd"
    },
    'lang_ru': {
        'start': "Выберите язык / Тилни танланг:",
        'chosen': "✅ Язык выбран! Теперь вы можете отправить голосовое сообщение или текст. Я классифицирую и сохранив их.",
        'wait': "⏳ Пожалуйста, подождите...",
        'ok': "✅ Сохранено!",
        'err': "❌ Произошла ошибка.",
        'err_auth': "❌ Проблема с API ключом.",
        'err_limit': "❌ Лимит исчерпан.",
        'history_title': "📜 Последние 10 записей:",
        'empty': "📭 Пока записей нет.",
        'category': "Тип",
        'content': "Содержание",
        'amount': "Сумма",
        'expense': "Расход",
        'task': "Задача",
        'note': "Заметка"
    }
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp DATETIME,
            category TEXT,
            content TEXT,
            amount REAL
        )
    ''')
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ўзбекча (кирилл)", callback_data="lang_uz_cyr")],
        [InlineKeyboardButton("O'zbekcha (lotin)", callback_data="lang_uz_lat")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru")],
    ]
    await update.message.reply_text(
        L['lang_uz_cyr']['start'],
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data["lang"] = lang
    texts = L.get(lang, L['lang_uz_cyr'])
    await query.edit_message_text(texts['chosen'])

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L['lang_uz_cyr'])
    question = update.message.text

    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    status_msg = await update.message.reply_text(texts['wait'])

    try:
        if not CLAUDE_API_KEY:
            await status_msg.edit_text(texts['err_auth'])
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

        system_prompt = f"""You are a personal assistant. Analyze the user's input and extract data into JSON.
Categories: 'expense' (харажат/расход), 'task' (вазифа/задача), 'note' (қайд/заметка).
Format: {{"category": "...", "content": "...", "amount": number or null}}
Rules:
1. 'content' should be a concise summary in the user's language ({lang}).
2. 'amount' is only for 'expense', otherwise null.
3. Return ONLY JSON."""

        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": question}]
        )

        res_text = message.content[0].text
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO records (user_id, timestamp, category, content, amount)
                VALUES (?, ?, ?, ?, ?)
            ''', (update.effective_user.id, datetime.now(), data['category'], data['content'], data.get('amount')))
            conn.commit()
            conn.close()

            cat_name = texts.get(data['category'], data['category'])
            amt_str = f"\n{texts['amount']}: {data['amount']}" if data.get('amount') else ""
            await status_msg.edit_text(f"{texts['ok']}\n\n<b>{cat_name}</b>: {data['content']}{amt_str}", parse_mode='HTML')
        else:
            await status_msg.edit_text(texts['err'])

    except Exception as e:
        logger.error(f"Text handling error: {e}")
        await status_msg.edit_text(texts['err'])

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L['lang_uz_cyr'])

    await update.message.reply_chat_action(constants.ChatAction.RECORD_VOICE)
    status_msg = await update.message.reply_text(texts['wait'])

    file_id = update.message.voice.file_id
    new_file = await context.bot.get_file(file_id)

    ogg_path = f"v_{update.effective_chat.id}_{update.message.message_id}.ogg"
    mp3_path = ogg_path.replace(".ogg", ".mp3")

    try:
        await new_file.download_to_drive(ogg_path)

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ffmpeg_exe, "-y", "-i", ogg_path, "-ar", "16000", mp3_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(mp3_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        system_prompt = f"""You are a personal assistant. Analyze the audio and extract data into JSON.
Categories: 'expense', 'task', 'note'.
Format: {{"category": "...", "content": "...", "amount": number or null}}
Rules:
1. 'content' summary in user's language ({lang}).
2. Return ONLY JSON."""

        message = client.messages.create(
            model=CLAUDE_MODEL,
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
                                "data": audio_data
                            }
                        },
                        {"type": "text", "text": "Extract data from this audio."}
                    ]
                }
            ]
        )

        res_text = message.content[0].text
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO records (user_id, timestamp, category, content, amount)
                VALUES (?, ?, ?, ?, ?)
            ''', (update.effective_user.id, datetime.now(), data['category'], data['content'], data.get('amount')))
            conn.commit()
            conn.close()

            cat_name = texts.get(data['category'], data['category'])
            amt_str = f"\n{texts['amount']}: {data['amount']}" if data.get('amount') else ""
            await status_msg.edit_text(f"{texts['ok']}\n\n<b>{cat_name}</b>: {data['content']}{amt_str}", parse_mode='HTML')
        else:
            await status_msg.edit_text(texts['err'])

    except Exception as e:
        logger.error(f"Voice handling error: {e}")
        await status_msg.edit_text(texts['err'])
    finally:
        if os.path.exists(ogg_path): os.remove(ogg_path)
        if os.path.exists(mp3_path): os.remove(mp3_path)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    texts = L.get(lang, L['lang_uz_cyr'])

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT category, content, amount, timestamp FROM records
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT 10
    ''', (update.effective_user.id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(texts['empty'])
        return

    msg = f"<b>{texts['history_title']}</b>\n\n"
    for row in rows:
        cat, content, amount, ts = row
        cat_name = texts.get(cat, cat)
        dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S.%f').strftime('%d.%m %H:%M')
        amt_str = f" ({amount})" if amount else ""
        msg += f"• [{dt}] <b>{cat_name}</b>: {html.escape(content)}{amt_str}\n"

    await update.message.reply_text(msg, parse_mode='HTML')

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    logger.info("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
