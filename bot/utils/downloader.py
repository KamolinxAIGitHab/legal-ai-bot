import yt_dlp
import os
import uuid

def download_reels_audio(url: str) -> str:
    """
    Downloads the audio from an Instagram Reel and returns the path to the file.
    Note: Since ffmpeg is not available, we download the best available format
    that contains audio and video, then treat it as a source for STT.
    OpenAI Whisper can handle mp4 files directly.
    """
    output_dir = "downloads"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    filename = f"{uuid.uuid4()}.mp4"
    filepath = os.path.join(output_dir, filename)

    ydl_opts = {
        'format': 'best',
        'outtmpl': filepath,
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return filepath
