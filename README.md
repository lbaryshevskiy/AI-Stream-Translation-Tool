# 🧠 AI Stream Translation Tool

This is a lightweight MVP that listens to a streamer’s microphone, transcribes speech using OpenAI's Whisper, translates it into English (or other languages), and displays the subtitles live as an overlay in OBS or Streamlabs.

---

## ⚙️ Features

- 🎤 Real-time microphone transcription with Whisper
- 🌍 Instant translation (Google Translate API via `googletrans`)
- 🖥️ Live subtitle overlay for OBS via browser source
- 🧪 Lightweight and local — no external servers required
- 💬 Currently supports English output (multi-language toggle coming soon)

---

## 📁 Project Structure
├── main.py # Main app logic (mic → subtitles)
├── requirements.txt # List of Python packages to install
├── templates/
│ └── overlay.html # Overlay file for OBS browser source
└── README.md # This file
---

## 🧪 How to Run (Mac Instructions)

### 1. Install dependencies

Install Python 3.10+ and [Homebrew](https://brew.sh), then run:

```bash
brew install ffmpeg
pip install -r requirements.txt

# Run the app
python main.py
The app will start listening to your microphone.

Every few seconds, it transcribes and translates what you say.

3. Set up OBS overlay
Open OBS

Add a Browser Source

Set the URL to: http://localhost:5000
