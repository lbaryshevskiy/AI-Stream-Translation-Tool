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

#Adding a stop button
stop_event = threading.Event()
backend_threads = []

selected_lang = tk.StringVar(value="en")  # default to English

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

import engineio.async_drivers.threading as eio_threading
import engineio.base_server

engineio.base_server.async_drivers = {'threading': eio_threading}

app = Flask(__name__)
print(">>> CONFIRM: async_mode is set to threading ✅")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# --- Flask Web Server ---
@app.route('/')
def overlay():
    return render_template('overlay.html')

@socketio.on('connect')
def test_connect():
    print("✅ Socket connected")
    socketio.emit("subtitle", {"text": "🔥 Hello from Streamsub!"})

def record_audio():
    print("🎤 record_audio() started")
    stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    while not stop_event.is_set():
        frames = []
        for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
            if stop_event.is_set():
                break
            data = stream.read(CHUNK)
            frames.append(data)
        audio_queue.put(b''.join(frames))
    stream.stop_stream()
    stream.close()
    print("🛑 record_audio() stopped")

def transcribe_loop():
    print("🧠 transcribe_loop() started")
    while not stop_event.is_set():
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
                    translated = translator.translate(text, dest=selected_lang.get()).text
                    print(f"🎙️ {text} → 💬 {translated}")
                    socketio.emit('subtitle', {'text': translated})
            except Exception as e:
                print(f"❌ Error in transcription/translation: {e}")
        time.sleep(1)
    print("🛑 transcribe_loop() stopped")

# --- Launch Backend Threads ---
def start_backend():
    global backend_threads
    print("🟢 start_backend() triggered")
    stop_event.clear()
    backend_threads = [
        threading.Thread(target=record_audio, daemon=True),
        threading.Thread(target=transcribe_loop, daemon=True),
        threading.Thread(target=lambda: socketio.run(app, host='0.0.0.0', port=5100, debug=False, use_reloader=False, allow_unsafe_werkzeug=True), daemon=True),
    ]
    for t in backend_threads:
        t.start()

def stop_backend():
    print("🔴 stop_backend() triggered")
    stop_event.set()

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

tk.Label(frame, text="Select translation language:").pack()

lang_menu = tk.OptionMenu(frame, selected_lang,
    "en", "es", "fr", "de", "it", "pt", "ru", "uk", "zh-cn", "ja")
lang_menu.pack(pady=(0, 10))

url_entry = tk.Entry(frame, width=40, justify='center')
url_entry.insert(0, "http://localhost:5100")
url_entry.config(state='readonly')
url_entry.pack(pady=(5, 5))

copy_btn = tk.Button(frame, text="📋 Copy URL", command=copy_url)
copy_btn.pack(pady=5)

def toggle_backend():
    if start_btn["text"].startswith("▶️"):
        start_backend()
        start_btn.config(text="⏹ Stop Subtitle App")
        status_label.config(text="🎙️ Transcription running...")
    else:
        stop_backend()
        start_btn.config(text="▶️ Start Subtitle App")
        status_label.config(text="⏹ Transcription stopped")

start_btn = tk.Button(frame, text="▶️ Start Subtitle App", command=toggle_backend)
start_btn.pack(pady=(10, 5))

status_label = tk.Label(frame, text="", fg="green")
status_label.pack()

if __name__ == "__main__":
    root.mainloop()


