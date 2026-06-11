# "Legal AI Bot" - Davlat Xaridlari Intellektual Tahlil Tizimi

Ushbu hujjat Oʻzbekiston Respublikasining davlat xaridlari sohasidagi qonunchiligi (ZRU-684 va unga oʻzgartirishlar) asosida ishlovchi intellektual Telegram bot loyihasining texnik arxitekturasini tavsiflaydi.

## 1. To'liq Texnik Arxitektura

Tizim quyidagi komponentlardan tashkil topadi:

*   **Frontend (Telegram Bot):** Foydalanuvchi interfeysi sifatida `aiogram` (Python) kutubxonasi yordamida yaratilgan bot.
*   **Backend API (FastAPI):** Asosiy mantiq, ma'lumotlar bazasi bilan ishlash va AI modelini boshqarish uchun.
*   **AI Engine:**
    *   **LLM:** OpenAI GPT-4o yoki GPT-4o-mini.
    *   **Orchestrator:** LangChain yoki LlamaIndex (RAG jarayonini boshqarish uchun).
*   **Ma'lumotlar Bazasi:**
    *   **PostgreSQL:** Foydalanuvchilar, loglar va limitlar uchun.
    *   **Vector DB (FAISS/Pinecone):** Qonunchilik hujjatlarining embeddinglarini saqlash uchun.
*   **Cache:** Redis (sessiyalarni saqlash uchun).

## 2. Ma'lumotlar Bazasi Sxemasi (Database Schema)

Asosiy jadvallar:
*   `users`: `id`, `telegram_id`, `full_name`, `organization_type`, `language`, `created_at`.
*   `procurement_logs`: `id`, `user_id`, `input_data` (JSON), `result` (JSON), `law_references`, `timestamp`.
*   `laws_vector`: `id`, `content_chunk`, `metadata` (modda, band), `embedding_vector`.
*   `limits`: `id`, `customer_type` (byudjet/korporativ), `procurement_method`, `min_amount`, `max_amount`, `bhm_multiplier`.

## 3. AI Workflow (Ishlash Mantig'i)

Tizim uchta bosqichda qaror qabul qiladi:
1.  **Rule-based Engine:** Foydalanuvchi kiritgan summa va tashkilot turini joriy BHM (Baza hisoblash miqdori) va qonuniy limitlar bilan solishtiradi.
2.  **RAG (Retrieval Augmented Generation):** Foydalanuvchi so'roviga mos keluvchi qonun moddalarini Vector DB dan qidirib topadi.
3.  **LLM Synthesis:** Qoidalar va topilgan qonun matnlari asosida foydalanuvchiga tushunarli tilda javob shakllantiradi.

## 4. Telegram Bot Ssenariylari

1.  `/start` -> Tilni tanlash (O'zbek/Rus/Ingliz).
2.  **Wizard (So'rovnoma):**
    *   Tashkilot turi? (Byudjet tashkiloti / Korporativ buyurtmachi).
    *   Mablag' manbasi? (Byudjet / O'z mablag'lari / Kredit).
    *   Xarid summasi? (Summada kiritiladi).
    *   Xarid obyekti? (Tovar / Ish / Xizmat).
    *   Maxsus holat? (Favqulodda / Import / Takroriy).
3.  **Natija:** Xarid turi (Elektron do'kon, Auksion, Tanlov, Tender yoki To'g'ridan-to'g'ri) va huquqiy asosi ko'rsatiladi.

## 5. UX Flow

*   **Minimalizm:** Foydalanuvchidan faqat zarur ma'lumotlar tugmalar (Inline Buttons) orqali so'raladi.
*   **Interaktivlik:** Har bir qadamda tushuntirishlar berib boriladi.
*   **Hujjatlash:** Natijani PDF shaklida yuklab olish imkoniyati.

## 6. API Struktura

*   `POST /api/v1/analyze`: Foydalanuvchi ma'lumotlarini qabul qilib, tahlil natijasini qaytaradi.
*   `GET /api/v1/laws`: Qonunchilik bazasidan qidirish.
*   `POST /api/v1/admin/update-limits`: BHM yoki limitlarni yangilash (Admin uchun).

## 7. MVP Rejasi

*   **1-bosqich:** Telegram bot bazasini yaratish va Wizard interfeysini sozlash (1 hafta).
*   **2-bosqich:** Davlat xaridlari qonunchiligini embedding qilish va Vector DB ga yuklash (1 hafta).
*   **3-bosqich:** Rule-based mantiqni (limitlar tahlili) integratsiya qilish (1 hafta).
*   **4-bosqich:** Tahlil natijasini shakllantirish va test qilish (1 hafta).

## 8. Monetizatsiya Modeli

*   **B2B (SaaS):** Tashkilotlar uchun yillik obuna.
*   **Freemium:** Oddiy maslahatlar bepul, PDF hisobot va hujjat shablonlari pullik.
*   **API Access:** Boshqa tizimlar (masalan, ERP) bilan integratsiya uchun pullik API.

## 9. Xavfsizlik Choraları

*   **Ma'lumotlar himoyasi:** Foydalanuvchi ma'lumotlarini shifrlangan holda saqlash.
*   **Loglash:** Barcha tahlil jarayonlarini audit uchun saqlash.
*   **Rate Limiting:** Botga bo'ladigan spam hujumlardan himoyalanish.

## 10. Masshtablash (Scalable Infrastructure)

*   **Dockerization:** Barcha xizmatlarni konteynerlarda ishlatish.
*   **Cloud Hosting:** AWS yoki DigitalOcean kabi platformalarda Kubernetes yordamida yuklamani boshqarish.
*   **CI/CD:** GitHub Actions orqali avtomatik testlash va deploy qilish.
