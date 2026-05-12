# legal-ai-bot
Compliance-first Legal AI Telegram bot

## Орнатиш (Installation)

1. Репозиторийни клонланг:
   ```bash
   git clone <repository-url>
   cd legal-ai-bot
   ```

2. Виртуал муҳит яратинг ва фаоллаштиринг:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # ёки
   venv\Scripts\activate  # Windows
   ```

3. Керакли кутубхоналарни ўрнатинг:
   ```bash
   pip install -r requirements.txt
   ```

4. Созламаларни созланг:
   `.env.example` файлини `.env` га нусхаланг ва `BOT_TOKEN` ни киритинг.

5. Ботни ишга туширинг:
   ```bash
   python main.py
   ```

## Лойиҳа тузилмаси

- `main.py` - Ботни ишга тушириш нуқтаси.
- `bot/` - Ботнинг асосий логикаси.
  - `handlers/` - Хабарларни қайта ишлаш.
  - `keyboards/` - Тугмалар.
  - `middlewares/` - Оралиқ дастурлар.
  - `utils/` - Ёрдамчи функциялар.
  - `config_reader.py` - Созламаларни ўқиш.
