import os
import re
import json
import sqlite3
import asyncio
from datetime import datetime

import speech_recognition as sr
from pydub import AudioSegment
import static_ffmpeg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
import anthropic

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
    await query.edit_message_text(
        "✅ Тил танланди!\n\nОвозли ёки матнли хабар юборинг, мен уни таҳлил қилиб сақлаб қўяман."
    )

static_ffmpeg.add_paths()

def init_db():
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS notes
                 (user_id INTEGER, type TEXT, content TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

def save_note(user_id, note_type, content):
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("INSERT INTO notes VALUES (?, ?, ?, ?)",
              (user_id, note_type, content, timestamp))
    conn.commit()
    conn.close()

def get_notes(user_id, limit=10):
    conn = sqlite3.connect("notes.db")
    c = conn.cursor()
    c.execute("SELECT type, content, timestamp FROM notes WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")

    status_msg = "🎙 Овозни қайта ишлаяпман..."
    if lang == "lang_uz_lat": status_msg = "🎙 Ovozni qayta ishlayapman..."
    elif lang == "lang_ru": status_msg = "🎙 Обрабатываю голос..."

    wait_msg = await update.message.reply_text(status_msg)

    ogg_file = f"voice_{update.message.voice.file_id}.ogg"
    wav_file = f"voice_{update.message.voice.file_id}.wav"

    try:
        voice = await update.message.voice.get_file()
        await voice.download_to_drive(ogg_file)

        audio = await asyncio.to_thread(AudioSegment.from_ogg, ogg_file)
        await asyncio.to_thread(audio.export, wav_file, format="wav")

        r = sr.Recognizer()
        with sr.AudioFile(wav_file) as source:
            audio_data = r.record(source)

            stt_lang = "uz-UZ"
            if lang == "lang_ru": stt_lang = "ru-RU"

            text = await asyncio.to_thread(r.recognize_google, audio_data, language=stt_lang)

        await process_note_ai(update, context, text, wait_msg)

    except Exception as e:
        err_msg = f"❌ Хатолик юз берди: {str(e)}"
        await wait_msg.edit_text(err_msg)
    finally:
        if os.path.exists(ogg_file): os.remove(ogg_file)
        if os.path.exists(wav_file): os.remove(wav_file)

async def process_note_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, content: str, wait_msg=None):
    lang = context.user_data.get("lang", "lang_uz_cyr")

    prompts = {
        "lang_uz_cyr": {
            "system": "Сиз фойдали ёрдамчисиз. Матнни таҳлил қилиб, уни 'expense' (харажат), 'task' (вазифа) ёки 'note' (эслатма) турига ажратинг. Жавобни ФАҚАТ JSON форматида беринг: {\"type\": \"...\", \"response\": \"қисқача хулоса\"}",
            "wait": "⏳ Таҳлил қилиняпти...",
            "success": "✅ Сақланди!",
            "type_labels": {"expense": "Харажат", "task": "Вазифа", "note": "Эслатма"}
        },
        "lang_uz_lat": {
            "system": "Siz foydali yordamchisiz. Matnni tahlil qilib, uni 'expense' (xarajat), 'task' (vazifa) yoki 'note' (eslatma) turiga ajrating. Javobni FAQAT JSON formatida bering: {\"type\": \"...\", \"response\": \"qisqacha xulosa\"}",
            "wait": "⏳ Tahlil qilinyapti...",
            "success": "✅ Saqlandi!",
            "type_labels": {"expense": "Xarajat", "task": "Vazifa", "note": "Eslatma"}
        },
        "lang_ru": {
            "system": "Вы полезный помощник. Проанализируйте текст и классифицируйте его как 'expense' (расход), 'task' (задача) или 'note' (заметка). Ответьте ТОЛЬКО в формате JSON: {\"type\": \"...\", \"response\": \"краткое описание\"}",
            "wait": "⏳ Анализирую...",
            "success": "✅ Сохранено!",
            "type_labels": {"expense": "Расход", "task": "Задача", "note": "Заметка"}
        }
    }

    p = prompts.get(lang, prompts["lang_uz_cyr"])

    if wait_msg:
        await wait_msg.edit_text(p["wait"])
    else:
        wait_msg = await update.message.reply_text(p["wait"])

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            system=p["system"],
            messages=[{"role": "user", "content": content}]
        )

        raw_res = message.content[0].text
        match = re.search(r'\{.*\}', raw_res, re.DOTALL)
        if match:
            data = json.loads(match.group())
            note_type = data.get("type", "note")
            ai_res = data.get("response", content)

            save_note(update.effective_user.id, note_type, content)

            label = p["type_labels"].get(note_type, note_type)
            await wait_msg.edit_text(f"{p['success']}\n\n📌 *{label}*: {ai_res}", parse_mode="Markdown")
        else:
            save_note(update.effective_user.id, "note", content)
            await wait_msg.edit_text(f"{p['success']}\n\n📝 {content}")

    except Exception as e:
        await wait_msg.edit_text(f"❌ Хато: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_note_ai(update, context, update.message.text)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    notes = get_notes(update.effective_user.id)

    if not notes:
        msg = "📭 Рўйхат бўш."
        if lang == "lang_uz_lat": msg = "📭 Ro'yxat bo'sh."
        elif lang == "lang_ru": msg = "📭 Список пуст."
        await update.message.reply_text(msg)
        return

    type_labels = {
        "lang_uz_cyr": {"expense": "Харажат", "task": "Вазифа", "note": "Эслатма"},
        "lang_uz_lat": {"expense": "Xarajat", "task": "Vazifa", "note": "Eslatma"},
        "lang_ru": {"expense": "Расход", "task": "Задача", "note": "Заметка"}
    }
    labels = type_labels.get(lang, type_labels["lang_uz_cyr"])

    text = "📜 *Охирги 10 та қайд:*\n\n"
    if lang == "lang_uz_lat": text = "📜 *Oxirgi 10 ta qayd:*\n\n"
    elif lang == "lang_ru": text = "📜 *Последние 10 записей:*\n\n"

    for n_type, content, ts in notes:
        dt = datetime.fromisoformat(ts).strftime("%d.%m %H:%M")
        label = labels.get(n_type, n_type)
        text += f"🔹 {dt} [{label}]: {content}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    notes = get_notes(update.effective_user.id, limit=50)

    if not notes:
        msg = "📭 Маълумот етарли эмас."
        if lang == "lang_uz_lat": msg = "📭 Ma'lumot yetarli emas."
        elif lang == "lang_ru": msg = "📭 Недостаточно данных."
        await update.message.reply_text(msg)
        return

    wait_msg = "📊 Анализ қиляпман..."
    if lang == "lang_uz_lat": wait_msg = "📊 Analiz qilyapman..."
    elif lang == "lang_ru": wait_msg = "📊 Анализирую..."

    status = await update.message.reply_text(wait_msg)

    content_list = [f"{n_type}: {content}" for n_type, content, ts in notes]
    all_content = "\n".join(content_list)

    system_prompts = {
        "lang_uz_cyr": "Сиз шахсий ёрдамчисиз. Қайдлар рўйхатидан келиб чиқиб, кунлик харажатлар, бажарилган ишлар ва муҳим эслатмалар бўйича қисқача (5-6 қатор) ҳисобот беринг. Фақат ўзбек тилида кириллда ёзинг.",
        "lang_uz_lat": "Siz shaxsiy yordamchisiz. Qaydlar ro'yxatidan kelib chiqib, kunlik xarajatlar, bajarilgan ishlar va muhim eslatmalar bo'yicha qisqacha (5-6 qator) hisobot bering. Faqat o'zbek tilida lotinda yozing.",
        "lang_ru": "Вы личный помощник. На основе списка записей составьте краткий (5-6 строк) отчет по расходам, задачам и заметкам. Отвечайте на русском языке."
    }

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            system=system_prompts.get(lang, system_prompts["lang_uz_cyr"]),
            messages=[{"role": "user", "content": f"Қайдлар:\n{all_content}"}]
        )
        await status.edit_text(message.content[0].text)
    except Exception as e:
        await status.edit_text(f"❌ Хато: {str(e)}")

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CallbackQueryHandler(language_chosen, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот ишга тушди...")
    app.run_polling()

if __name__ == "__main__":
    main()
