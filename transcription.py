import av
import speech_recognition as sr
import os

def convert_ogg_to_wav(ogg_path, wav_path):
    input_container = av.open(ogg_path)
    output_container = av.open(wav_path, 'w')

    stream = input_container.streams.audio[0]
    out_stream = output_container.add_stream('pcm_s16le', rate=16000)
    out_stream.channels = 1

    for frame in input_container.decode(stream):
        for packet in out_stream.encode(frame):
            output_container.mux(packet)

    for packet in out_stream.encode(None):
        output_container.mux(packet)

    input_container.close()
    output_container.close()

def transcribe_audio(wav_path, lang_code):
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
        try:
            # lang_code expects values like 'uz-UZ' or 'ru-RU'
            text = recognizer.recognize_google(audio_data, language=lang_code)
            return text
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"STT Error: {e}")
            return None

def process_voice(ogg_path, lang="lang_uz_cyr"):
    wav_path = ogg_path.replace(".ogg", ".wav")

    # Map telegram lang to STT lang
    lang_map = {
        "lang_uz_cyr": "uz-UZ",
        "lang_uz_lat": "uz-UZ",
        "lang_ru": "ru-RU"
    }
    stt_lang = lang_map.get(lang, "uz-UZ")

    try:
        convert_ogg_to_wav(ogg_path, wav_path)
        text = transcribe_audio(wav_path, stt_lang)
        return text
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
