# main.py
# MVP: Transcribes microphone audio, translates to English, and sends captions to OBS overlay

import whisper
import pyaudio
import wave
import threading
import time
import os
import queue
from flask import Flask, render_template
from flask_socketio import SocketIO
from googletrans import Translator

# Load Whisper model
model = whisper.load_model("base")
translator = Translator()

# Flask app and SocketIO setup
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Queue for audio chunks
audio_queue = queue.Queue()

# Audio recording setup
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
RECORD_SECONDS = 5
WAVE_OUTPUT_FILENAME = "temp.wav"

p = pyaudio.PyAudio()
stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

# Background audio recording thread
def record_audio():
    while True:
        frames = []
        for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
            data = stream.read(CHUNK)
            frames.append(data)
        audio_queue.put(b''.join(frames))

threading.Thread(target=record_audio, daemon=True).start()

# Transcription and translation loop
def transcribe_loop():
    while True:
        if not audio_queue.empty():
            audio_data = audio_queue.get()
            with wave.open(WAVE_OUTPUT_FILENAME, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(p.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(audio_data)

            try:
                result = model.transcribe(WAVE_OUTPUT_FILENAME)
                text = result['text'].strip()
                if text:
                    translated = translator.translate(text, dest='en').text
                    print(f"🔊 {text} → 🗣️ {translated}")
                    socketio.emit('subtitle', {'text': translated}, broadcast=True)
            except Exception as e:
                print(f"Error: {e}")
        time.sleep(1)

threading.Thread(target=transcribe_loop, daemon=True).start()

# Serve overlay page
@app.route('/')
def overlay():
    return render_template('overlay.html')

# Run Flask app
@socketio.on('connect')
def test_connect():
    print("✅ Socket connected")
    socketio.emit("subtitle", "🔥 Hello from server!")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5100)

