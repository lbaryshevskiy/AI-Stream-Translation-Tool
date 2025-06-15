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
import customtkinter as ctk
import json
import os

SETTINGS_FILE = "settings.json"

# --- DEVELOPMENT MODE ---
dev_mode = True
dev_override_plan = "studio"  # can be: "free", "studio", "creator"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)

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

start_btn = None
status_label = None
selected_lang = None

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
    
def show_pro_preferences():
    popup = ctk.CTkToplevel()
    popup.title("Settings")
    popup.geometry("380x380")

    from __main__ import dev_mode, dev_override_plan
    user_plan = dev_override_plan if dev_mode else "free"

    tabview = ctk.CTkTabview(popup, width=360, height=300)
    tabview.pack(padx=10, pady=10, fill="both", expand=True)

    # Always add both tabs
    tabview.add("Studio")
    tabview.add("Creator")

    # --- STUDIO TAB ---
    try:
        studio_tab = tabview.tab("Studio")

        # Font Size
        ctk.CTkLabel(studio_tab, text="Subtitle Font Size:").pack(pady=(10, 0))
        font_size_value = ctk.CTkLabel(studio_tab, text="24")
        font_size_value.pack()
        font_size_slider = ctk.CTkSlider(studio_tab, from_=12, to=48, number_of_steps=8,
                                         command=lambda val: font_size_value.configure(text=str(int(float(val)))))
        font_size_slider.set(24)
        font_size_slider.pack(pady=(0, 10))

        ctk.CTkLabel(studio_tab, text="Overlay Opacity:").pack(pady=(5, 0))
        opacity_value = ctk.CTkLabel(studio_tab, text="1.00")
        opacity_value.pack()
        opacity_slider = ctk.CTkSlider(studio_tab, from_=0.2, to=1.0,
                                       command=lambda val: opacity_value.configure(text=f"{float(val):.2f}"))
        opacity_slider.set(1.0)
        opacity_slider.pack(pady=(0, 10))

        # Font Color (locked preview for Studio)
        # Font Color row with tooltip "?" next to label
        color_frame = ctk.CTkFrame(studio_tab, fg_color="transparent")
        color_frame.pack(pady=(10, 0), anchor="w")

        ctk.CTkLabel(color_frame, text="Font Color:").pack(side="left")

        # Tooltip logic
        # Tooltip logic (correct indentation inside try:)
        tooltip = None

        def show_tooltip(event):
            nonlocal tooltip
            tooltip = ctk.CTkToplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.configure(bg="gray10")
            tooltip_label = ctk.CTkLabel(
                tooltip,
                text="Unlock this option in Creator version",
                font=("Helvetica", 9, "italic"),
                text_color="gray"
            )
            tooltip_label.pack()
            tooltip.geometry(f"+{event.x_root + 10}+{event.y_root + 10}")

        def hide_tooltip(event):
            nonlocal tooltip
            if tooltip:
                tooltip.destroy()
                tooltip = None

        tooltip_icon = ctk.CTkLabel(color_frame, text="?", width=16)
        tooltip_icon.pack(side="left", padx=5)
        tooltip_icon.bind("<Enter>", show_tooltip)
        tooltip_icon.bind("<Leave>", hide_tooltip)

        # Disabled dropdown
        color_menu = ctk.CTkOptionMenu(
            studio_tab,
            values=["White", "Yellow", "Cyan", "Green"]
        )
        color_menu.set("White")
        color_menu.configure(state="disabled")
        color_menu.pack(pady=(5, 10))

         # Dark mode
        def toggle_dark_mode():
            mode = "Dark" if dark_mode_switch.get() == 1 else "Light"
            ctk.set_appearance_mode(mode)
            save_settings({"appearance_mode": mode})

        dark_mode_switch = ctk.CTkSwitch(
            studio_tab,
            text="Dark Mode",
            command=toggle_dark_mode
        )
        dark_mode_switch.select()  # ON by default (Dark mode enabled)
        dark_mode_switch.pack(pady=10)
        
    except KeyError:
        pass

    try:
        creator_tab = tabview.tab("Creator")

        ctk.CTkLabel(creator_tab, text="Whisper Model:").pack(pady=(10, 0))
        model_menu = ctk.CTkOptionMenu(creator_tab, values=["tiny", "base", "small", "medium", "large"])
        model_menu.set("base")
        model_menu.pack(pady=(0, 10))

        logging_switch = ctk.CTkSwitch(creator_tab, text="Enable Logging")
        logging_switch.pack(pady=10)

        save_checkbox = ctk.CTkCheckBox(creator_tab, text="Save Settings to File")
        save_checkbox.pack(pady=10)

        if user_plan != "creator":
            model_menu.configure(state="disabled")
            logging_switch.configure(state="disabled")
            save_checkbox.configure(state="disabled")

            upgrade_label = ctk.CTkLabel(
                creator_tab,
                text="🔒 Unlock these features with Creator Version",
                font=("Helvetica", 15, "italic"),
                text_color="gray"
            )
            upgrade_label.place(relx=0.5, rely=1.0, anchor="s", y=-10)

        
    except KeyError:
         pass
    
    # --- SAVE BUTTON ---
    ctk.CTkButton(popup, text="Save & Close", command=popup.destroy).pack(pady=10)

def launch_overlay():
    webbrowser.open("http://localhost:5100")

# --- Customtkinter GUI ---
def toggle_backend():
    if start_btn.cget("text").startswith("▶️"):
        start_backend()
        start_btn.configure(text="⏹ Stop Subtitle App")
        status_label.configure(text="🎙️ Transcription running...")
    else:
        stop_backend()
        start_btn.configure(text="▶️ Start Subtitle App")
        status_label.configure(text="⏹ Transcription stopped")

def main():
    settings = load_settings()
    appearance = settings.get("appearance_mode", "Dark")
    ctk.set_appearance_mode(appearance)
    ctk.set_default_color_theme("blue")

    global root, selected_lang, start_btn, status_label

    root = ctk.CTk()
    root.title("Streamsub")
    root.geometry("300x300")
    root.resizable(False, False)

    # Determine plan (simulate during dev)
    if dev_mode:
        user_plan = dev_override_plan
    else:
        user_plan = "free"  # placeholder for future licensing logic

    frame = ctk.CTkFrame(root)
    frame.pack(padx=20, pady=20, fill="both", expand=True)
    
    plan_colors = {
        "free": "red",
        "studio": "orange",
        "creator": "green"
    }

    # === Plan label container (bottom-right inside frame) ===
    plan_wrapper = ctk.CTkFrame(
        frame,
        fg_color="transparent",
        corner_radius=0
    )
    plan_wrapper.place(relx=1.0, rely=1.0, anchor="se", x=-5, y=7)

    plan_label = ctk.CTkLabel(
        plan_wrapper,
        text=f"{user_plan.title()} Version",
        text_color=plan_colors.get(user_plan, "gray"),
        font=("Helvetica", 12, "italic"),
        fg_color="transparent"
    )
    plan_label.pack(padx=0, pady=2)

    ctk.CTkLabel(frame, text="🎙️ Streamsub", font=("Helvetica", 16, "bold")).pack(pady=(0, 10))

    selected_lang = ctk.StringVar(value="🌐 Language")
    lang_menu = ctk.CTkOptionMenu(
        frame,
        variable=selected_lang,
        values=["Select Language..."] + list(language_options.keys())
    )
    lang_menu.pack(pady=10)

    copy_btn = ctk.CTkButton(frame, text="📋 Copy OBS URL", command=copy_url)
    copy_btn.pack(pady=10)

    settings_btn = ctk.CTkButton(frame, text="⚙️ Preferences (Pro)", command=show_pro_preferences)
    settings_btn.pack(pady=10)

    start_btn = ctk.CTkButton(frame, text="▶️ Start", command=toggle_backend)
    start_btn.pack(pady=10)
    

    root.mainloop()

if __name__ == "__main__":
    main()



