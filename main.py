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

language_options = {
    "🇬🇧 English": "en",
    "🇪🇸 Spanish": "es",
    "🇫🇷 French": "fr",
    "🇩🇪 German": "de",
    "🇮🇹 Italian": "it",
    "🇵🇹 Portuguese": "pt",
    "🇺🇦 Ukrainian": "uk",
    "🇨🇳 Chinese": "zh-cn",
    "🇯🇵 Japanese": "ja"
}


#Adding a stop button
stop_event = threading.Event()
backend_threads = []

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
                    lang_label = selected_lang.get()
                    lang_code = language_options.get(lang_label)

                    if lang_code:
                        translated = translator.translate(text, dest=lang_code).text
                        print(f"🎙️ {text} → 💬 {translated}")
                        socketio.emit('subtitle', {'text': translated})
                    else:
                        print("⚠️ No valid language selected.")
            except Exception as e:
                print(f"❌ Error in transcription/translation: {e}")

                  


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
root.geometry("250x300")
root.resizable(True, True)

frame = tk.Frame(root, padx=20, pady=20)
frame.grid(row=0, column=0, sticky="nsew")
root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(0, weight=1)

frame.grid_rowconfigure((0,1,2,3,4,5), weight=1)
frame.grid_columnconfigure((0,1), weight=1)

# Header
header = tk.Label(frame, text="🎙️ Streamsub", font=("Helvetica", 16, "bold"))
header.grid(row=0, column=0, columnspan=2, pady=(0, 10))

# Language selection
tk.Label(frame, text="Translate subtitles to:", font=("Helvetica", 10)).grid(row=1, column=0, sticky="e")
selected_lang = tk.StringVar(value="Select Language")
lang_menu = tk.OptionMenu(frame, selected_lang, *language_options.keys())
lang_menu.config(width=17)
lang_menu.grid(row=0, column=0, pady=(20, 15), padx=20, sticky="w")

# OBS URL
tk.Label(frame, text="Paste in OBS Browser Source:", font=("Helvetica", 10)).grid(row=2, column=0, sticky="e")
url_entry = tk.Entry(frame, width=32, justify="center", font=("Courier", 10))
url_entry.insert(0, "http://localhost:5100")
url_entry.config(state="readonly")
url_entry.grid(row=2, column=1, sticky="w")

copy_btn = tk.Button(frame, text="📋 Copy URL", command=copy_url, width=15)
copy_btn.grid(row=1, column=0, pady=5, padx=20, sticky="w")

def toggle_backend():
    if start_btn["text"].startswith("▶️"):
        start_backend()
        start_btn.config(text="⏹ Stop Subtitle App")
        status_label.config(text="🎙️ Transcription running...")
    else:
        stop_backend()
        start_btn.config(text="▶️ Start Subtitle App")
        status_label.config(text="⏹ Transcription stopped")

# Start/Stop Button
start_btn = tk.Button(frame, text="▶️ Start Subtitle App", command=toggle_backend, width=15)
start_btn.grid(row=2, column=0, pady=(10, 20), padx=20, sticky="w")

# Status label
status_label = tk.Label(frame, text="", font=("Helvetica", 9), fg="green")
status_label.grid(row=5, column=0, columnspan=2)

if __name__ == "__main__":
    root.mainloop()


