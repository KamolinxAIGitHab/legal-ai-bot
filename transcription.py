import av
import speech_recognition as sr
import io
import wave

def transcribe_audio(file_path, lang='uz-UZ'):
    """
    Converts OGG/OPUS to WAV using PyAV with proper resampling,
    and then transcribes using SpeechRecognition.
    """
    try:
        container = av.open(file_path)
        stream = container.streams.audio[0]

        # Define resampler: convert to s16 (16-bit PCM), mono, 16000Hz (standard for STT)
        resampler = av.audio.resampler.AudioResampler(
            format='s16',
            layout='mono',
            rate=16000,
        )

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2) # 16-bit
            wav_file.setframerate(16000)

            for frame in container.decode(audio=0):
                resampled_frames = resampler.resample(frame)
                for resampled_frame in resampled_frames:
                    wav_file.writeframes(resampled_frame.to_ndarray().tobytes())

        wav_buffer.seek(0)

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_buffer) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language=lang)
            return text

    except Exception as e:
        print(f"Transcription error: {e}")
        return None

if __name__ == "__main__":
    pass
