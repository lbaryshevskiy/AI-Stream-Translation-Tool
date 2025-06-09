import whisper
import pyaudio
import wave
import threading
import time
import queue
from flask import Flask, render_template
from flask_socketio import SocketIO
from googletrans import Translator
pa = pyaudio.PyAudio()

# --- Audio Configuration ---
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
RECORD_SECONDS = 5
WAVE_OUTPUT_FILENAME = "temp.wav"

# --- Load Models ---
model = whisper.load_model("base")
translator = Translator()

# --- Flask App Setup ---
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
audio_queue = queue.Queue()

# --- Audio Recording Thread ---
def record_audio():
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True, frames_per_buffer=CHUNK)
    while True:
        frames = []
        for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
            data = stream.read(CHUNK)
            frames.append(data)
        audio_queue.put(b''.join(frames))

# --- Transcription Thread ---
def transcribe_loop():
    while True:
        if not audio_queue.empty():
            audio_data = audio_queue.get()
            with wave.open(WAVE_OUTPUT_FILENAME, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(pa.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(audio_data)

            try:
                result = model.transcribe(WAVE_OUTPUT_FILENAME)
                text = result['text'].strip()
                if text:
                    translated = translator.translate(text, dest='en').text
                    print(f"🎙️ {text} → 💬 {translated}")
                    socketio.emit('subtitle', {'text': translated}, broadcast=True)
            except Exception as e:
                print(f"❌ Error in transcription/translation: {e}")
        time.sleep(1)

# --- Serve Web Overlay ---
@app.route('/')
def overlay():
    return render_template('overlay.html')

# --- SocketIO Connect Handler ---
@socketio.on('connect')
def test_connect():
    print("✅ Socket connected")
    socketio.emit("subtitle", {"text": "🔥 Hello from server!"})

# --- Start Threads ---
threading.Thread(target=record_audio, daemon=True).start()
threading.Thread(target=transcribe_loop, daemon=True).start()

# --- Run App ---
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5100, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)


