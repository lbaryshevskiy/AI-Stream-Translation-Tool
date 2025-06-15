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
    popup.geometry("430x430")

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
        label_font = ("Helvetica", 13, "bold")

                # === Studio Page Container ===
                 # === Studio Page Container and Pages ===
        studio_pages = ctk.CTkFrame(studio_tab, fg_color="transparent")
        studio_pages.pack(expand=True, fill="both")

        page1 = ctk.CTkFrame(studio_pages, fg_color="transparent")
        page2 = ctk.CTkFrame(studio_pages, fg_color="transparent")

        page1.pack(expand=True, fill="both")  # Initial visible page

                # === Subtitle Font Size ===
        
        ctk.CTkLabel(page1, text="Subtitle Font Size:", font=label_font).pack(pady=(10, 0))

        font_size_value_label = ctk.CTkLabel(page1, text="24")
        font_size_value_label.pack()

        def update_font_size(value):
            font_size_value_label.configure(text=str(int(value)))

        font_slider = ctk.CTkSlider(
            page1,
            from_=10,
            to=40,
            number_of_steps=6,
            command=update_font_size
        )
        font_slider.set(24)
        font_slider.pack(pady=(0, 10))

        # === Overlay Opacity ===
        ctk.CTkLabel(page1, text="Overlay Opacity:", font=label_font).pack(pady=(10, 0))

        opacity_value_label = ctk.CTkLabel(page1, text="1.00")
        opacity_value_label.pack()

        def update_opacity(value):
            opacity_value_label.configure(text=f"{float(value):.2f}")

        opacity_slider = ctk.CTkSlider(
            page1,
            from_=0.2,
            to=1.0,
            number_of_steps=8,
            command=update_opacity
        )
        opacity_slider.set(1.0)
        opacity_slider.pack(pady=(0, 10))

        
        # === Font Color (with Tooltip) ===
        tooltip = None

        def show_tooltip(event):
            nonlocal tooltip
            tooltip = ctk.CTkToplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.configure(bg="gray10")
            tooltip_label = ctk.CTkLabel(
                tooltip,
                text="Unlock this option in Creator version",
                font=("Helvetica", 10, "italic"),
                text_color="gray"
            )
            tooltip_label.pack()
            tooltip.geometry(f"+{event.x_root + 10}+{event.y_root + 10}")

        def hide_tooltip(event):
            nonlocal tooltip
            if tooltip:
                tooltip.destroy()
                tooltip = None

        # Label and tooltip row
        color_label_frame = ctk.CTkFrame(page1, fg_color="transparent")
        color_label_frame.pack(pady=(10, 0))

        font_color_label = ctk.CTkLabel(color_label_frame, text="Font Color:", font=label_font)
        font_color_label.pack(side="left")

        tooltip_icon = ctk.CTkLabel(color_label_frame, text="?", font=("Helvetica", 12, "bold"), width=12)
        tooltip_icon.pack(side="left", padx=(2, 0))
        tooltip_icon.bind("<Enter>", show_tooltip)
        tooltip_icon.bind("<Leave>", hide_tooltip)

        # Disabled dropdown
        color_menu = ctk.CTkOptionMenu(
            page1,
            values=["White", "Yellow", "Cyan", "Green"]
        )
        color_menu.set("White")
        color_menu.configure(state="disabled")
        color_menu.pack(pady=(5, 10))

        def toggle_dark_mode():
            mode = "Dark" if dark_mode_switch.get() == 1 else "Light"
            ctk.set_appearance_mode(mode)
            save_settings({"appearance_mode": mode})


        def go_to_page2():
            page1.pack_forget()
            page2.pack(expand=True, fill="both")
            back_btn.place(relx=0.0, rely=1.0, anchor="sw", x=10, y=-10)
            next_btn.place_forget()

        def go_to_page1():
            page2.pack_forget()
            page1.pack(expand=True, fill="both")
            next_btn.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)
            back_btn.place_forget()


        next_btn = ctk.CTkButton(
            studio_tab,
            text="→",
            width=30,
            height=25,
            corner_radius=6,
            command=go_to_page2
        )
        next_btn.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)

        back_btn = ctk.CTkButton(
            studio_tab,
            text="←",
            width=30,
            height=25,
            corner_radius=6,
            command=go_to_page1
        )

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
            
        footer_frame = ctk.CTkFrame(popup, fg_color="transparent")
        footer_frame.pack(pady=(5, 10), fill="x")

        # Inner frame to hold buttons right-aligned
        right_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        right_frame.pack(side="right", padx=(0, 30))

        dark_mode_switch = ctk.CTkSwitch(
            right_frame,
            text="Dark Mode",
            command=toggle_dark_mode
        )
        dark_mode_switch.select()
        dark_mode_switch.pack(side="right", padx=(16, 0))

        save_btn = ctk.CTkButton(
            right_frame,
            text="Save & Close",
            command=popup.destroy,
            width=140
        )
        save_btn.pack(side="right")


        
    except KeyError:
         pass


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



