from faster_whisper import WhisperModel
import sys

# Ladda KB-Whisper large med GPU (CUDA)
print("Laddar KB-Whisper large modell på GPU...")
model = WhisperModel("KBLab/kb-whisper-large", device="cuda", compute_type="float16")

# Transkribera
audio_file = r"E:\Transkribera\Mamma waw isolerad.wav"
print(f"Transkriberar: {audio_file}")

segments, info = model.transcribe(audio_file, language="sv")

print(f"Detekterat språk: {info.language} (sannolikhet: {info.language_probability:.2f})")

# Spara som SRT
srt_file = r"E:\Transkribera\Mamma waw isolerad.srt"

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

with open(srt_file, "w", encoding="utf-8") as f:
    for i, segment in enumerate(segments, start=1):
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        text = segment.text.strip()
        f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
        print(f"[{start} --> {end}] {text}")

print(f"\nKlart! SRT-fil sparad: {srt_file}")
