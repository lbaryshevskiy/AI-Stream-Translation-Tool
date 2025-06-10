import tkinter as tk
import threading
import queue
import time
import wave
import whisper
import pyaudio
from flask import Flask, render_template
from flask_socketio import SocketIO
from googletrans import Translator
import webbrowser
import os

# --- Global Setup ---
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
RECORD_SECONDS = 5
WAVE_OUTPUT_FILENAME = "temp.wav"
pa = pyaudio.PyAudio()

model = whisper.load_model("base")
translator = Translator()
audio_queue = queue.Queue()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# --- Flask Web Server ---
@app.route('/')
def overlay():
    return render_template('overlay.html')

@socketio.on('connect')
def test_connect():
    print("✅ Socket connected")
    socketio.emit("subtitle", {"text": "🔥 Hello from Streamsub!"})

def record_audio():
    stream = pa.open(format=FORMAT, channels=CHANNELS,
                     rate=RATE, input=True, frames_per_buffer=CHUNK)
    while True:
        frames = []
        for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
            data = stream.read(CHUNK)
            frames.append(data)
        audio_queue.put(b''.join(frames))

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
                    socketio.emit('subtitle', {'text': translated})
            except Exception as e:
                print(f"❌ Error in transcription/translation: {e}")
        time.sleep(1)

# --- Launch Backend Threads ---
def start_backend():
    threading.Thread(target=record_audio, daemon=True).start()
    threading.Thread(target=transcribe_loop, daemon=True).start()
    threading.Thread(target=lambda: socketio.run(app, host='0.0.0.0', port=5100, debug=False, use_reloader=False, allow_unsafe_werkzeug=True), daemon=True).start()

# --- GUI ---
def copy_url():
    root.clipboard_clear()
    root.clipboard_append("http://localhost:5100")
    status_label.config(text="✅ Copied to clipboard!")

def launch_overlay():
    webbrowser.open("http://localhost:5100")

root = tk.Tk()
root.title("Streamsub")
root.geometry("420x220")
root.resizable(False, False)

frame = tk.Frame(root, padx=20, pady=20)
frame.pack()

tk.Label(frame, text="🎙️ Streamsub - AI-Powered Subtitles", font=("Helvetica", 16)).pack(pady=(0, 10))
tk.Label(frame, text="Paste this in OBS Browser Source:").pack()

url_entry = tk.Entry(frame, width=40, justify='center')
url_entry.insert(0, "http://localhost:5100")
url_entry.config(state='readonly')
url_entry.pack(pady=(5, 5))

copy_btn = tk.Button(frame, text="📋 Copy URL", command=copy_url)
copy_btn.pack(pady=5)

start_btn = tk.Button(frame, text="▶️ Start Subtitle App", command=start_backend)
start_btn.pack(pady=(10, 5))

status_label = tk.Label(frame, text="", fg="green")
status_label.pack()

root.mainloop()

