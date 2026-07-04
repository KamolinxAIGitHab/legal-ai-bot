import os, re, json, sqlite3, base64, subprocess, imageio_ffmpeg, html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import anthropic

TOKEN, CLAUDE_API_KEY = os.environ.get("TOKEN"), os.environ.get("CLAUDE_API_KEY")
L = {
    'lang_uz_cyr': {'chosen': "✅ Тил танланди! Овозли хабар юборинг:", 'wait': "⏳ Кутинг...", 'ok': "✅ Сақланди!", 'history': "📜 Қайдлар:", 'err': "❌ Хато."},
    'lang_uz_lat': {'chosen': "✅ Til tanlandi! Ovozli xabar yuboring:", 'wait': "⏳ Kuting...", 'ok': "✅ Saqlandi!", 'history': "📜 Qaydlar:", 'err': "❌ Xato."},
    'lang_ru': {'chosen': "✅ Выбран! Отправьте голос:", 'wait': "⏳ Ждите...", 'ok': "✅ Сохранено!", 'history': "📜 Записи:", 'err': "❌ Ошибка."}
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(n, callback_data=c)] for n, c in [("Ўзбекча (кирилл)", "lang_uz_cyr"), ("O'zbekcha (lotin)", "lang_uz_lat"), ("Русский", "lang_ru")]]
    await update.message.reply_text("Тилни танланг / Выберите язык:", reply_markup=InlineKeyboardMarkup(keyboard))

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["lang"] = query.data
    await query.edit_message_text(L[query.data]['chosen'])

def init_db():
    with sqlite3.connect("records.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, category TEXT, content TEXT, amount REAL)")

def transcode_to_mp3(ogg_path, mp3_path):
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", ogg_path, "-acodec", "libmp3lame", mp3_path]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def clean_markdown(text):
    text = re.sub(r'#{1,6}\s?', '', text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("*", "").replace("_", "")
    text = text.replace("`", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msg = L.get(lang, L['lang_uz_cyr'])
    status = await update.message.reply_text(msg['wait'])
    ogg, mp3 = f"v_{update.effective_chat.id}_{update.message.message_id}.ogg", f"v_{update.effective_chat.id}_{update.message.message_id}.mp3"
    try:
        await (await update.message.voice.get_file()).download_to_drive(ogg)
        transcode_to_mp3(ogg, mp3)
        with open(mp3, "rb") as f: audio_b64 = base64.b64encode(f.read()).decode("utf-8")
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = "Analyze voice and return ONLY JSON with keys: category (expense/task/note), content, amount (number or null)."
        res = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            extra_headers={"anthropic-beta": "audio-2024-10-31"},
            system=prompt,
            messages=[{"role": "user", "content": [{"type": "audio", "source": {"type": "base64", "media_type": "audio/mpeg", "data": audio_b64}}]}]
        )
        res_text = res.content[0].text
        data = json.loads(re.search(r'\{.*\}', res_text, re.DOTALL).group())
        with sqlite3.connect("records.db") as conn:
            conn.execute("INSERT INTO records (user_id, category, content, amount) VALUES (?, ?, ?, ?)", (update.effective_user.id, data['category'], data['content'], data.get('amount')))
        await status.edit_text(f"{msg['ok']}\n\n<b>{data['category'].upper()}</b>: {data['content']}" + (f"\n💰 {data['amount']}" if data.get('amount') else ""), parse_mode="HTML")
    except Exception as e:
        await status.edit_text(f"{msg['err']}: {str(e)}")
    finally:
        for f in [ogg, mp3]:
            if os.path.exists(f): os.remove(f)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    msg = L.get(lang, L['lang_uz_cyr'])
    with sqlite3.connect("records.db") as conn:
        rows = conn.execute("SELECT category, content, amount, timestamp FROM records WHERE user_id = ? ORDER BY id DESC LIMIT 10", (update.effective_user.id,)).fetchall()
    if not rows: return await update.message.reply_text("📭")
    text = f"<b>{msg['history']}</b>\n\n"
    for c, cnt, a, t in rows:
        text += f"📅 {t[:16]} | <b>{c.upper()}</b>\n{html.escape(cnt)}" + (f" | 💰 {a}\n" if a else "\n") + "--- \n"
    await update.message.reply_text(text, parse_mode="HTML")

async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "lang_uz_cyr")
    question = update.message.text

    if lang == "lang_uz_cyr":
        system = """Сиз Ўзбекистон давлат харидлари ва қонунчилик бўйича мутахассиссиз.
Қатъий қоидалар:
1. Фақат ўзбек тилида, кирилл алифбосида ёзинг
2. Лотин ҳарфларини ИШЛАТМАНГ
3. Грамматик хатоларсиз ёзинг
4. Барча сўзлар тўғри кирилл алифбосида бўлсин
5. Рақамли рўйхат билан аниқ жавоб беринг
6. Markdown белгиларини ИШЛАТМАНГ
7. Оддий текст форматида ёзинг
8. Номаълум бўлса — расмий манбага мурожаат қилинг денг"""

    elif lang == "lang_uz_lat":
        system = """Siz O'zbekiston davlat xaridlari va qonunchilik bo'yicha mutaxasssissiz.
Qoidalar:
1. O'zbek tilida lotin alifbosida javob bering
2. Markdown belgilarini ISHLATMANG
3. Oddiy tekst formatida yozing
4. Noma'lum bo'lsa — rasmiy manbaga murojaat qiling deng"""

    else:
        system = """Вы эксперт по государственным закупкам и законодательству Узбекистана.
Правила:
1. Отвечайте на русском языке
2. НЕ используйте Markdown
3. Пишите обычным текстом
4. Если не уверены — напишите: Обратитесь к официальному источнику"""

    await update.message.reply_text("⏳ Жавоб тайёрланмоқда...")

    try:
        if not CLAUDE_API_KEY:
            await update.message.reply_text(
                "❌ CLAUDE_API_KEY топилмади. Railway Variables ни текширинг."
            )
            return

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        answer = clean_markdown(message.content[0].text)
        await update.message.reply_text(
            f"🤖 {answer}\n\n⚠️ Жавоблар умумий ва таълимий мақсадда."
        )

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
