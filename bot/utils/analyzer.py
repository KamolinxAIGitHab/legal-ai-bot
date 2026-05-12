from openai import OpenAI
from bot.config import settings

client = OpenAI(api_key=settings.openai_api_key)

def analyze_content(text: str) -> str:
    """
    Analyzes the transcribed text and provides a verdict in Uzbek.
    """
    prompt = (
        "Siz Instagram Reels videolarini tahlil qiluvchi mutaxassissiz. "
        "Quyidagi matn Instagram Reelsdan olingan ovozli xabar transkripsiyasi. "
        "Sizning vazifangiz:\n"
        "1. Matndagi asosiy g'oya va fikrni aniqlash.\n"
        "2. Ushbu g'oya yoki yo'nalishni o'rganishga arziydimi yoki yo'qmi, shuni baholash.\n"
        "3. Foydaliligi haqida qisqacha xulosa berish.\n\n"
        "Javobni faqat o'zbek tilida bering.\n\n"
        f"Matn: {text}"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Siz foydali maslahatlar beruvchi yordamchisiz."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content
