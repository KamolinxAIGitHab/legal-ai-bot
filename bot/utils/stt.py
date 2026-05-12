from openai import OpenAI
from bot.config import settings

client = OpenAI(api_key=settings.openai_api_key)

def transcribe_audio(file_path: str) -> str:
    """
    Transcribes the audio from the given file path using OpenAI Whisper.
    """
    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
    return transcript.text
