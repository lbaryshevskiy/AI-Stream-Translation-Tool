import threading
import queue
import time
time.sleep(0.5)
import wave
import whisper
import pyaudio
from flask import Flask, render_template
from flask_socketio import SocketIO
import webrtcvad
import numpy as np
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)
import customtkinter as ctk
import json
import os
from googletrans import Translator
from faster_whisper import WhisperModel
clear_timer = None  # Global timer to auto-clear subtitle

SETTINGS_FILE = "settings.json"
is_in_settings = False
flask_thread = None

subtitles_started = False

vad = webrtcvad.Vad()
vad.set_mode(2)  # Aggressiveness 0-3 (2 is moderate suppression)

# --- DEVELOPMENT MODE ---
dev_mode = True
dev_override_plan = "creator"

user_plan = dev_override_plan if dev_mode else "free"

def run_flask():
    socketio.run(app, port=5100, allow_unsafe_werkzeug=True)

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
RATE = 32000
RECORD_SECONDS = 5
WAVE_OUTPUT_FILENAME = "temp.wav"
pa = pyaudio.PyAudio()

from pynput import keyboard

overlay_visible = True

global wordcount_label
wordcount_label = None

total_word_count = 0
total_char_count = 0


def toggle_overlay():
    global overlay_visible
    overlay_visible = not overlay_visible
    if overlay_visible:
        print("✅ Subtitle overlay shown.")
    else:
        print("✅ Subtitle overlay hidden.")

audio_paused = False

def toggle_audio_pause():
    global audio_paused
    audio_paused = not audio_paused
    if audio_paused:
        print("⏸️ Audio capture paused.")
    else:
        print("▶️ Audio capture resumed.")

# === Hotkey state tracking ===
current_keys = set()

def on_press(key):
    try:
        current_keys.add(key)
        check_hotkeys()
    except AttributeError:
        pass

def on_release(key):
    try:
        current_keys.remove(key)
    except KeyError:
        pass

def check_hotkeys():
    settings = load_settings()

    startstop_keys = parse_hotkey(settings.get("startstop_hotkey", "ctrl+p"))
    overlay_keys = parse_hotkey(settings.get("overlay_hotkey", "ctrl+o"))
    pause_keys = parse_hotkey(settings.get("pause_hotkey", "ctrl+shift+p"))

    if all(k in current_keys for k in startstop_keys):
        toggle_backend()

    if all(k in current_keys for k in overlay_keys):
        toggle_overlay()

    if all(k in current_keys for k in pause_keys):
        toggle_audio_pause()

def parse_hotkey(hotkey_str):
    keys = []
    parts = hotkey_str.lower().split("+")
    for part in parts:
        if part == "ctrl":
            keys.append(keyboard.Key.ctrl_l)
        elif part == "shift":
            keys.append(keyboard.Key.shift)
        elif part == "alt":
            keys.append(keyboard.Key.alt_l)
        elif part == "cmd":
            keys.append(keyboard.Key.cmd)
        else:
            keys.append(keyboard.KeyCode.from_char(part))
    return keys


settings = load_settings()
settings = load_settings()
current_model_name = settings.get("whisper_model", "base")

if current_model_name.startswith("faster"):
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
else:
    model = whisper.load_model(current_model_name)

# --- WHISPERX PATCH ---
import torch
import whisperx
device = "cuda" if torch.cuda.is_available() else "cpu"
whisperx_model = None
align_model = None
align_metadata = None

# Force language from input settings (not from output lang selection)
input_settings = load_settings()
input_lang = input_settings.get("input_language", "🌐 Auto-detect").strip()
forced_lang_code = language_options.get(input_lang, None)

# Transcription block
if current_model_name.startswith("faster"):
    if forced_lang_code:
        segments, _ = whisper_model.transcribe(WAVE_OUTPUT_FILENAME, language=forced_lang_code)
    else:
        segments, _ = whisper_model.transcribe(WAVE_OUTPUT_FILENAME)

    text = " ".join([segment.text for segment in segments]).strip()
    print(f"🟦 Transcribed (Faster-Whisper): {text}")
else:
    if forced_lang_code:
        result = model.transcribe(WAVE_OUTPUT_FILENAME, language=forced_lang_code)
    else:
        result = model.transcribe(WAVE_OUTPUT_FILENAME)

    text = " ".join([segment["text"] for segment in result["segments"]]).strip()
    print(f"🟨 Transcribed: {text}")


translator = Translator()
audio_queue = queue.Queue()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
print(f">>> CONFIRM: async_mode is set to {socketio.async_mode} ✅")

loading_popup = None

def show_loading_popup(message="Loading, please wait..."):
    global loading_popup
    loading_popup = ctk.CTkToplevel()
    loading_popup.title("Please Wait")
    loading_popup.geometry("300x100")
    loading_popup.resizable(False, False)
    ctk.CTkLabel(loading_popup, text=message).pack(expand=True)
    loading_popup.update()

def close_loading_popup():
    global loading_popup
    if loading_popup:
        loading_popup.destroy()
        loading_popup = None
        
# --- Flask Web Server ---
@app.route('/')
def overlay():
    return render_template('overlay.html')

@socketio.on('connect')
def test_connect():
    print("✅ Socket connected")
    def emit_hello():
        try:
            socketio.emit("subtitle", {"text": "✨ Streamsub is live!"})
            settings = load_settings()
            socketio.emit("style_update", {
                "font": settings.get("font_family", "Inter"),
                "size": settings.get("font_size", 20),
                "opacity": settings.get("opacity", 0.8),
                "wraplength": settings.get("wraplength", 1000),
                "box_background": bool(settings.get("box_background", True)),
                "font_color": settings.get("font_color", "white"),
            })
        except Exception as e:
            print(f"⚠️ OBS closed or emit failed: {e}")
    threading.Timer(0.1, emit_hello).start()


def record_audio():
    print("🎤 record_audio() started")
    try:
        stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        while not stop_event.is_set():
            frames = []
            for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)

            audio_data = b''.join(frames)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            processed_audio = audio_array.astype(np.int16).tobytes()

            #print("✅ Queuing audio data (bypassing VAD for debug)")
            audio_queue.put(audio_data)

    except Exception as e:
        print("❌ Error in record_audio():", e)
    finally:
        stream.stop_stream()
        stream.close()
        print("🛑 record_audio() stopped")
        
def clear_subtitle():
    global subtitles_started
    if not subtitles_started:
        return 
    socketio.emit("subtitle", {"text": ""})
    print("🕓 No speech detected — subtitle cleared.")

def transcribe_loop():
    print("🧠 transcribe_loop() started")
    global total_word_count, total_char_count, wordcount_label
    while not stop_event.is_set():
        if not audio_queue.empty():
            #print("🔄 transcribe_loop() processing audio data...")
            audio_data = audio_queue.get()
            #print("🎤 Processing audio data from queue, size:", len(audio_data))
            with wave.open(WAVE_OUTPUT_FILENAME, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(pa.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(audio_data)

            try:
                if current_model_name == "faster-tiny":
                    segments, info = model.transcribe(WAVE_OUTPUT_FILENAME)
                    text = " ".join([segment.text for segment in segments]).strip()
                    print(f"📝 Transcribed (Faster-Whisper): {text}")
                else:
                    result = model.transcribe(WAVE_OUTPUT_FILENAME)
                    text = " ".join([segment["text"] for segment in result["segments"]]).strip()
                    print(f"📝 Transcribed: {text}")

                words = text.split()
                total_word_count += len(words)
                total_char_count += len(text)
                
                if user_plan == "free" and char_count_label is not None:
                    remaining = max(0, 250000 - total_char_count)
                    char_count_label.configure(text=f"Characters remaining: {remaining:,}")
                    if remaining == 0:
                        char_count_label.configure(
                            text="Free access expired – Click here to upgrade",
                            text_color="blue",
                            font=("Helvetica", 12, "underline")
                        )
                        def open_upgrade(event):
                            import webbrowser
                            webbrowser.open("https://yourwebsite.com/upgrade")  # placeholder
                    
                        char_count_label.bind("<Button-1>", open_upgrade)
                    
                        socketio.emit("subtitle", {"text": "Free access expired – Click here to upgrade"})
                        stop_backend()

                if wordcount_label and wordcount_label.winfo_exists():
                    def update_label():
                        wordcount_label.configure(
                            text=f"Words: {total_word_count} | Characters: {total_char_count}"
                        )
                    wordcount_label.after(0, update_label)

                if text:
                    lang_label = selected_lang.get().strip()
                    lang_code = language_options.get(lang_label, "en")
                    translated = translator.translate(text, dest=lang_code).text
                    print(f"🌐 Translation: {translated}")
                    socketio.emit("subtitle", {"text": translated})
                else:
                    print("⚠️ Whisper returned empty text.")

            except Exception as e:
                print("❌ Transcription or emission error:", e)

            time.sleep(0.1)  # avoid busy loop

# --- Launch Backend Threads ---
def start_backend():
    global backend_threads
    print("🟢 start_backend() triggered")
    stop_event.clear()

    global total_word_count, total_char_count
    total_word_count = 0
    total_char_count = 0

    audio_thread = threading.Thread(target=record_audio, daemon=True)
    transcribe_thread = threading.Thread(target=transcribe_loop, daemon=True)

    backend_threads = [audio_thread, transcribe_thread]

    for t in backend_threads:
        t.start()
        
    start_flask_once()

    settings = load_settings()
    socketio.emit("style_update", {
        "font": settings.get("font_family", "Inter"),
        "size": settings.get("font_size", 20),
        "opacity": settings.get("opacity", 0.8),
        "wraplength": settings.get("wraplength", 1000),
        "box_background": settings.get("box_background", True),
        "font_color": settings.get("font_color", "white"),
    })

    
def stop_backend():
    global backend_threads, flask_thread
    print("🔴 stop_backend() triggered")
    stop_event.set()

    for t in backend_threads:
        if t.is_alive():
            print(f"⏳ Waiting for thread: {t.name}")
            t.join(timeout=3)
            if t.is_alive():
                print(f"⚠️ WARNING: Thread did not stop cleanly: {t.name}")

    backend_threads = []

    if flask_thread and flask_thread.is_alive():
        print("🛑 Flask thread still alive — not force-stopping in thread mode.")
      
def start_flask_once():
    global flask_thread
    if flask_thread is None or not flask_thread.is_alive():
        flask_thread = threading.Thread(
            target=lambda: socketio.run(
                app,
                host="0.0.0.0",
                port=5100,
                debug=False,
                use_reloader=False,
                allow_unsafe_werkzeug=True
            ),
            daemon=True
        )
        flask_thread.start()
        print("🚀 Flask started once")
    else:
        print("⚠️ Flask already running")

# --- GUI ---
def copy_url():
    root.clipboard_clear()
    root.clipboard_append("http://localhost:5100")
    status_label.configure(text="✅ Copied to clipboard!")
    
def show_pro_preferences():
    global is_in_settings
    is_in_settings = True
    popup = ctk.CTkToplevel()
    popup.title("Settings")
    popup.geometry("430x480")

    from __main__ import dev_mode, dev_override_plan
    user_plan = dev_override_plan if dev_mode else "free"


    tabview = ctk.CTkTabview(
        popup,
        width=360,
        height=300,
        fg_color="transparent"
    )
    tabview.add("Studio")
    tabview.add("Creator")

    tabview.pack(pady=15, padx=15, fill="both", expand=True)
    
    # Apply purple theme to tabs
    tabview._segmented_button.configure(
        fg_color="#6A1B9A",
        selected_color="#AB47BC",
        selected_hover_color="#AB47BC",
        unselected_color="#6A1B9A",
        unselected_hover_color="#AB47BC",
        text_color="white"
    )

    try:
        # Load saved settings
        settings = load_settings()
        saved_size = settings.get("font_size", 20)
        saved_opacity = settings.get("opacity", 0.1)
        
        studio_tab = tabview.tab("Studio")
        label_font = ("Helvetica", 13, "bold")

        studio_pages = ctk.CTkFrame(studio_tab, fg_color="transparent")
        studio_pages.pack(expand=True, fill="both")

        page1 = ctk.CTkFrame(studio_pages, fg_color="transparent")
        page2 = ctk.CTkFrame(studio_pages, fg_color="transparent")

        page1.pack(expand=True, fill="both")

                # --- Font Size ---
        def update_font_size(value):
            font_size_value_label.configure(text=str(int(float(value))))
            update_preview()

        font_size_label = ctk.CTkLabel(page1, text="Subtitle Font Size:", font=label_font)
        font_size_label.pack(pady=(15, 0))

        font_size_value_label = ctk.CTkLabel(page1, text=str(saved_size))
        font_size_value_label.pack(pady=(0, 2))

        font_slider = ctk.CTkSlider(
            page1,
            from_=12,
            to=48,
            number_of_steps=36,
            command=update_font_size,
            fg_color="#6A1B9A",
            progress_color="#AB47BC",
            button_color="#6A1B9A",
            button_hover_color="#AB47BC"
        )

        settings = load_settings()
        saved_size = settings.get("font_size", 20)
        if isinstance(saved_size, list):  # due to prior tuple saving
            saved_size = saved_size[0]
            
        font_slider.set(saved_size)
        font_slider.pack(pady=(0, 8))

        # --- Opacity ---
        opacity_label = ctk.CTkLabel(page1, text="Overlay Opacity:")
        opacity_label.pack(pady=(10, 0))
        
        saved_opacity = settings.get("opacity", 0.1)
        if isinstance(saved_opacity, list):
            saved_opacity = saved_opacity[0]
        
        overlay_opacity_slider = ctk.CTkSlider(
            page1,
            from_=0.1,
            to=1.0,
            number_of_steps=18,
            fg_color="#6A1B9A",
            progress_color="#AB47BC",
            button_color="#6A1B9A",
            button_hover_color="#AB47BC"
        )
        overlay_opacity_slider.set(saved_opacity)
        
        opacity_value_label = ctk.CTkLabel(page1, text=f"{saved_opacity:.2f}")
        opacity_value_label.pack(pady=(0, 2))
        
        overlay_opacity_slider.pack(pady=(0, 8))
        
        # --- Tooltip Definitions (must come before used) ---
        def show_tooltip(event):
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
            event.widget.tooltip = tooltip

        def hide_tooltip(event):
            if hasattr(event.widget, "tooltip"):
                event.widget.tooltip.destroy()

              # --- Font Color ---
        color_label_frame = ctk.CTkFrame(page1, fg_color="transparent")
        color_label_frame.pack(pady=(5, 0))
        
        font_color_label = ctk.CTkLabel(color_label_frame, text="Font Color:")
        font_color_label.pack(side="left")
        
        tooltip_icon = ctk.CTkLabel(
            color_label_frame,
            text="?",
            font=("Helvetica", 12, "bold"),
            width=12
        )
        tooltip_icon.pack(side="left", padx=(5, 0))
        
        if user_plan != "creator":
            tooltip_icon.bind("<Enter>", show_tooltip)
            tooltip_icon.bind("<Leave>", hide_tooltip)
        
        # Purple styled dropdown
        color_menu = ctk.CTkOptionMenu(
            page1,
            values=[
                "White", "Yellow", "Cyan", "Green",
                "Black", "Red", "Blue", "Orange", "Purple", "Pink"
            ],
            fg_color="#6A1B9A",
            button_color="#6A1B9A",
            button_hover_color="#AB47BC",
            text_color="white"
        )
        
        # Restore saved color
        saved_color = settings.get("font_color", "White").capitalize()
        if saved_color in ["White", "Yellow", "Cyan", "Green", "Black", "Red", "Blue", "Orange", "Purple", "Pink"]:
            color_menu.set(saved_color)
        else:
            color_menu.set("White")
        
        # Disable if needed
        if user_plan == "studio":
            color_menu.configure(state="disabled")
        
        color_menu.pack(pady=(0, 5))

        # --- Preview Box ---
        font_family_var = ctk.StringVar(value="Inter")
        
        preview_label = None
        # --- Live Preview Logic ---
        def update_preview(*args):
            if preview_label is None:
                return
            appearance = ctk.get_appearance_mode()
            font_color = "black" if appearance == "Light" else "white"

            preview_label.configure(
                font=(font_family_var.get(), 20),
                text_color=font_color
            )

            preview_frame.configure(fg_color="transparent")

            if not is_in_settings:
                current_settings = load_settings()
                socketio.emit("style_update", {
                    "font": font_family_var.get(),
                    "size": int(font_slider.get()),
                    "opacity": opacity,
                    "wraplength": current_settings.get("wraplength", 1000),
                    "box_background": current_settings.get("box_background", True),
                    "font_color": current_settings.get("font_color", "white"),
                })

        def update_opacity(value):
            opacity_value_label.configure(text=f"{float(value):.2f}")
            update_preview()

        overlay_opacity_slider.configure(command=update_opacity)
        
        
        def toggle_dark_mode():
            mode = "Dark" if dark_mode_switch.get() == 1 else "Light"
            ctk.set_appearance_mode(mode)
            save_settings({"appearance_mode": mode})
            # Immediately update preview font color
            update_preview()

            # Immediately update arrow color
            arrow_color = "white" if mode == "Dark" else "black"
            next_btn.configure(text_color=arrow_color)
            back_btn.configure(text_color=arrow_color)

        
        def go_to_page2():
            page1.pack_forget()
            page2.pack(expand=True, fill="both")
            page2.update_idletasks()
            
            back_btn.place(relx=0.0, rely=1.0, anchor="sw", x=10, y=-10)
            back_btn.update_idletasks()
            
            next_btn.place_forget()

        def go_to_page1():
            page2.pack_forget()
            page1.pack(expand=True, fill="both")
            page2.update_idletasks()
            
            back_btn.place_forget()
            next_btn.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)
            next_btn.update_idletasks()

        input_lang_label = ctk.CTkLabel(page1, text="Input Language:", font=label_font)
        input_lang_label.pack(pady=(15, 0))

        saved_input_lang = settings.get("input_language", "🌐 Auto-detect")
        input_lang_var = ctk.StringVar(value=saved_input_lang)

        input_lang_menu = ctk.CTkOptionMenu(
            page1,
            variable=input_lang_var,
            values=["🌐 Auto-detect"] + list(language_options.keys()),
            fg_color="#6A1B9A",
            button_color="#6A1B9A",
            button_hover_color="#AB47BC",
            text_color="white"
        )
        input_lang_menu.pack(pady=(0, 5))

        back_btn = ctk.CTkButton(
            studio_tab,
            text="←",
            width=30,
            height=25,
            fg_color="#6A1B9A", 
            hover_color="#AB47BC", 
            text_color="white", 
            corner_radius=8,
            command=go_to_page1,
        )
        back_btn.place(relx=0.0, rely=1.0, anchor="sw", x=10, y=-10)
        back_btn.place_forget()
    
        next_btn = ctk.CTkButton(
            studio_tab,
            text="→",
            width=30,
            height=25,
            fg_color="#6A1B9A",
            hover_color="#AB47BC",
            text_color="white", 
            corner_radius=8,
            command=go_to_page2,
        )
        next_btn.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)
        next_btn.update_idletasks()

        arrow_color = "black" if ctk.get_appearance_mode() == "Light" else "white"

        next_btn.configure(text_color=arrow_color)
        back_btn.configure(text_color=arrow_color)

        # --- Page 2: Box Size Selector ---

        def update_box_size(choice):
            if "Custom" in choice:
                width_entry.delete(0, ctk.END)
                custom_frame.pack(pady=(5, 10))
            else:
                custom_frame.pack_forget()
                wrap_length = box_size_presets.get(choice, 600)
                preview_label.configure(wraplength=wrap_length)

        # Create a horizontal frame for label + icon
        box_size_label_frame = ctk.CTkFrame(page2, fg_color="transparent")
        box_size_label_frame.pack(pady=(15, 0))
        
        box_size_label = ctk.CTkLabel(box_size_label_frame, text="Subtitle Box Size:", font=label_font)
        box_size_label.pack(side="left")
        
        wraplength_tooltip_icon = ctk.CTkLabel(box_size_label_frame, text="?", font=("Helvetica", 12, "bold"), width=12)
        wraplength_tooltip_icon.pack(side="left", padx=(4, 0))

        def show_wraplength_tooltip(event):
            tooltip = ctk.CTkToplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.configure(bg="gray10")
            tooltip_label = ctk.CTkLabel(
                tooltip,
                text="Check OBS Browser Sourcce => Properties, if encountering issues.",
                font=("Helvetica", 10, "italic"),
                text_color="gray"
            )
            tooltip_label.pack()
            tooltip.geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
            event.widget.tooltip = tooltip


        def hide_wraplength_tooltip(event):
            if hasattr(event.widget, "tooltip"):
                event.widget.tooltip.destroy()

        wraplength_tooltip_icon.bind("<Enter>", show_wraplength_tooltip)
        wraplength_tooltip_icon.bind("<Leave>", hide_wraplength_tooltip)

        box_size_presets = {
            "Compact (600x100)": 600,
            "Wide (800x100)": 800,
            "Tall (600x300)": 600,
            "Extended Width (1000x150)": 1000,
            "Full Width (1500x150)": 1500,
            "Custom...": None
        }

        settings = load_settings()
        saved_wrap = settings.get("wraplength", 1000)
        saved_box = settings.get("box_size", "Full Width (1000x150)")
        
        box_size_var = ctk.StringVar(value=saved_box)

        # Create a horizontal container
        box_size_container = ctk.CTkFrame(page2, fg_color="transparent")
        box_size_container.pack(pady=(0, 5))
        
        box_size_menu = ctk.CTkOptionMenu(
            box_size_container,
            variable=box_size_var,
            values=list(box_size_presets.keys()),
            command=update_box_size
        )
        box_size_menu.pack(side="left", padx=(15, 10))

        custom_frame = ctk.CTkFrame(box_size_container, fg_color="transparent")

        width_entry = ctk.CTkEntry(custom_frame, placeholder_text="Width", width=80)
        width_entry.pack(side="left", padx=(0, 5))

        apply_btn = ctk.CTkButton(
            custom_frame,
            text="Apply",
            width=60,
            command=lambda: apply_custom_width(),
            fg_color="#9C27B0",
            hover_color="#BA68C8",
            text_color="white",
            corner_radius=8
        )
        apply_btn.pack(side="left")
        custom_frame.pack_forget()

        # --- Font Family Selector ---
        font_choices = ["Helvetica", "Trebuchet MS", "Roboto", "Georgia", "Courier New", "Times New Roman"]
        
        saved_font = load_settings().get("font_family")
        if saved_font in font_choices:
            font_family_var.set(saved_font)

        def update_font_family(choice):
            preview_label.configure(font=(choice, 20))
            save_settings({"font_family": font_family_var.get()})

        font_family_label = ctk.CTkLabel(page2, text="Font Family:", font=label_font)
        font_family_label.pack(pady=(10, 0))

        font_family_menu = ctk.CTkOptionMenu(
            page2,
            values=font_choices,
            variable=font_family_var,
            command=update_font_family
        )
        font_family_menu.pack(pady=(0, 10))

        box_bg_var = ctk.BooleanVar(value=settings.get("box_background", True))
        box_bg_toggle = ctk.CTkCheckBox(
            page2,
            text="Enable Subtitle Background Box",
            variable=box_bg_var
        )
        box_bg_toggle.pack(pady=(20, 20))

        # --- Preview Box (moved from page1 to page2) ---
        preview_frame = ctk.CTkFrame(page2, fg_color="transparent", corner_radius=10, width=500, height=150)
        preview_frame.pack(pady=(15, 30), padx=40)
        update_preview()
        
        preview_label = ctk.CTkLabel(
            preview_frame,
            text="This is how your subtitle looks.",
            font=(font_family_var.get(), 20),
            fg_color="transparent",
            width=600,
            wraplength=600,
            anchor="center",
            justify="center"
        )
        preview_label.pack(pady=(30, 10))
    
        if saved_box == "Custom...":
            last_custom = settings.get("last_custom_box_size", f"{saved_wrap}x100")
            width_entry.insert(0, last_custom)
            custom_frame.pack(side="left", padx=(10, 0))
        else:
            custom_frame.pack_forget()
        
        def update_opacity(value):
            opacity_value_label.configure(text=f"{float(value):.2f}")
            update_preview()

        overlay_opacity_slider.configure(command=update_opacity)
        update_preview()

        def update_box_size(choice):
            if choice == "Custom...":
                width_entry.delete(0, ctk.END)
                custom_frame.pack(side="left", padx=(10, 0))
            else:
                custom_frame.pack_forget()
                wrap_length = box_size_presets.get(choice, 600)
                preview_label.configure(wraplength=wrap_length)

        def toggle_dark_mode():
            mode = "Dark" if dark_mode_switch.get() == 1 else "Light"
            ctk.set_appearance_mode(mode)
            save_settings({"appearance_mode": mode})

            # Update preview color immediately
            update_preview()

            # Update arrow colors immediately
            arrow_color = "white" if mode == "Dark" else "black"
            next_btn.configure(text_color=arrow_color)
            back_btn.configure(text_color=arrow_color)

        def apply_custom_width():
            value = width_entry.get().strip()
            try:
                if "x" in value:
                    width_str, _ = value.lower().split("x")
                    width = int(width_str.strip())
                else:
                    width = int(value)
                
                preview_label.configure(wraplength=width)
                box_size_var.set(f"Custom Width ({value}px)")
                save_settings({
                    "box_size": f"{value}px",
                    "last_custom_box_size": value
                })
                custom_frame.pack_forget()
        
            except Exception as e:
                print("Invalid custom size:", e)


    # --- CREATOR TAB ---
        creator_tab = tabview.tab("Creator")

        ctk.CTkLabel(creator_tab, text="Whisper Model:").pack(pady=(10, 0))

        model_menu = ctk.CTkOptionMenu(
            creator_tab,
            values=["Faster-Tiny","Tiny", "Base", "Small", "Medium", "Large"],
            fg_color="#6A1B9A",
            button_color="#6A1B9A",
            button_hover_color="#AB47BC",
            text_color="white"
        )
        saved_model = settings.get("whisper_model", "Base").capitalize()
        model_menu.set(saved_model if saved_model in ["Faster-Tiny", "Tiny", "Base", "Small", "Medium", "Large"] else "Base")
        model_menu.pack(pady=(0, 10))

        whisper_models = {
            "Faster-Tiny": "faster-tiny",
            "Tiny": "tiny",
            "Base": "base",
            "Small": "small",
            "Medium": "medium",
            "Large": "large"
        }

        def change_model(choice):
            global model, current_model_name
            print(f"🔄 Changing Whisper model to: {choice}")
            show_loading_popup("Loading model, please wait...")
            try:
                selected_model = whisper_models.get(choice, "faster-tiny")
                current_model_name = selected_model
                if selected_model == "faster-tiny":
                    model = WhisperModel("tiny", device="cpu", compute_type="int8")
                else:
                    model = whisper.load_model(selected_model)
                print(f"✅ Model switched to {selected_model}")
            except Exception as e:
                print(f"❌ Failed to load model '{selected_model}': {e}")
            finally:
                close_loading_popup()

                
        model_menu.configure(command=change_model)

        logging_switch = ctk.CTkSwitch(creator_tab, text="Enable Logging")
        logging_switch.pack(pady=10)

                # VAD Sensitivity Slider Label
        vad_label = ctk.CTkLabel(creator_tab, text="Speech Detection Sensitivity:")
        vad_label.pack(pady=(10, 0))
        
        # Dynamic VAD mode value label
        vad_value_label = ctk.CTkLabel(creator_tab, text="2")  # default mode
        vad_value_label.pack(pady=(0, 0))
        
        # VAD Slider
        vad_slider = ctk.CTkSlider(
            creator_tab,
            from_=0,
            to=3,
            number_of_steps=3,
            fg_color="#6A1B9A",
            progress_color="#AB47BC",
            button_color="#6A1B9A",
            button_hover_color="#AB47BC"
        )
        vad_slider.set(2)  # set default mode
        vad_slider.pack(pady=(0, 10))
        
        def update_vad(value):
            vad_mode = int(float(value))
            vad.set_mode(vad_mode)
            vad_value_label.configure(text=str(vad_mode))
        
        vad_slider.configure(command=update_vad)
        
        # --- Hotkey Settings ---
        hotkey_btn = ctk.CTkButton(
            creator_tab,
            text="Configure Hotkeys",
            command=open_hotkey_window,
            fg_color="#6A1B9A",
            hover_color="#AB47BC",
            text_color="white",
            corner_radius=8
        )
        hotkey_btn.pack(pady=(10, 0))

        saved_hotkey = settings.get("transcription_hotkey", "")

        livecount_title = ctk.CTkLabel(
            creator_tab,
            text="Live Count Usage:",
            font=("Helvetica", 13, "bold"),
        )
        livecount_title.pack(pady=(20, 0))  # reduced top padding, no bottom padding
        
        global wordcount_label
        wordcount_label = ctk.CTkLabel(creator_tab, text="Words: 0 | Characters: 0")
        wordcount_label.pack(pady=(0, 15))

        if user_plan == "studio":
            model_menu.configure(state="disabled")
            logging_switch.configure(state="disabled")
            vad_slider.configure(state="disabled")
            hotkey_btn.configure(state="disabled")

        footer_frame = ctk.CTkFrame(popup, fg_color="transparent")
        footer_frame.pack(pady=(5, 10), fill="x")

        right_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        right_frame.pack(side="right", padx=(100, 25))

        dark_mode_switch = ctk.CTkSwitch(
            right_frame,
            text="Dark Mode",
            command=toggle_dark_mode,
            progress_color="#AB47BC"  # Purple instead of default blue
        )

        if ctk.get_appearance_mode() == "Dark":
            dark_mode_switch.select()
        else:
            dark_mode_switch.deselect()

        dark_mode_switch.pack(side="right", padx=(10, 0))

        def close_settings():
            global is_in_settings
            is_in_settings = False
            popup.destroy()

        def save_and_close():
            existing = load_settings()
            font_size = int(font_slider.get())
            opacity = float(overlay_opacity_slider.get())
            font_family = font_family_var.get()
            existing["vad_mode"] = int(float(vad_slider.get()))
            vad.set_mode(existing["vad_mode"])
            
            box_choice = box_size_var.get()
                                
            if "Custom" in box_choice:
                width_str = width_entry.get().strip()
                wraplength = int(width_str.split("x")[0]) if "x" in width_str else int(width_str)
                existing["last_custom_box_size"] = width_str
            else:
                wraplength = box_size_presets.get(box_choice, 600)
                
            existing.update({
                "font_size": font_size,
                "opacity": opacity,
                "font_family": font_family,
                "box_size": box_choice,
                "last_custom_box_size": width_entry.get().strip() if "Custom" in box_choice else "",
                "input_language": input_lang_var.get(),
                "box_background": box_bg_var.get(),
                "font_color": color_menu.get().lower(),
            })

            existing["whisper_model"] = model_menu.get().lower()
            
            existing["box_size"] = box_choice
            if "Custom" in box_choice:
                existing["last_custom_box_size"] = width_entry.get().strip()
            else:
                existing["last_custom_box_size"] = ""

            save_settings(existing)

            # Emit updated style to the overlay stream
            socketio.emit("style_update", {
                "font": font_family,
                "size": font_size,
                "opacity": opacity,
                "wraplength": wraplength,
                "box_background": box_bg_var.get(),
                "font_color": color_menu.get().lower(),
            })
            custom_frame.pack_forget()
            global is_in_settings
            is_in_settings = False
            popup.destroy()


        save_btn = ctk.CTkButton(
            right_frame,
            text="Save & Close",
            command=save_and_close,
            width=140,
            fg_color="#9C27B0",
            hover_color="#BA68C8",
            text_color="white",
            corner_radius=8
        )
        save_btn.pack(side="right", padx=(20, 10), pady=5, anchor="center") 
    except KeyError:
        pass

def launch_overlay():
    webbrowser.open("http://localhost:5100")

# --- Customtkinter GUI ---
def toggle_backend():
    global status_label

    if start_btn.cget("text").startswith("▶️"):
        start_backend()
        start_btn.configure(text="⏹ Stop")
        if status_label:
            status_label.configure(text="🎙️ Transcription running...")
    else:
        stop_backend()
        start_btn.configure(text="▶️ Start")
        if status_label:
            status_label.configure(text="⏹ Transcription stopped")

            
def stop_flask():
    print("🛑 stop_flask() called (no killing)")
            
def restart_server():
    print("🔁 Restarting backend...")
    stop_event.set()
    stop_backend()
    time.sleep(1)
    stop_event.clear()
    start_flask_once()  # 🟢 Only restart Flask, not audio threads
    print("✅ Restart complete")

def open_hotkey_window():
    hotkey_window = ctk.CTkToplevel()
    hotkey_window.title("Hotkey Settings")
    hotkey_window.geometry("300x320")

    # Start/Stop Transcription Hotkey
    startstop_label = ctk.CTkLabel(hotkey_window, text="Start/Stop Transcription Hotkey:")
    startstop_label.pack(pady=(10, 0))

    startstop_entry = ctk.CTkEntry(hotkey_window, placeholder_text="e.g. ctrl+shift+s")
    startstop_entry.pack(pady=(0, 10))

    # Show/Hide Overlay Hotkey
    overlay_label = ctk.CTkLabel(hotkey_window, text="Show/Hide Overlay Hotkey:")
    overlay_label.pack(pady=(10, 0))

    overlay_entry = ctk.CTkEntry(hotkey_window, placeholder_text="e.g. ctrl+shift+o")
    overlay_entry.pack(pady=(0, 10))

    # Pause/Resume Audio Capture Hotkey
    pause_label = ctk.CTkLabel(hotkey_window, text="Pause/Resume Audio Capture Hotkey:")
    pause_label.pack(pady=(10, 0))

    pause_entry = ctk.CTkEntry(hotkey_window, placeholder_text="e.g. ctrl+shift+p")
    pause_entry.pack(pady=(0, 10))

    # Load saved hotkeys if exist
    saved_hotkeys = load_settings()
    startstop_entry.insert(0, saved_hotkeys.get("startstop_hotkey", ""))
    overlay_entry.insert(0, saved_hotkeys.get("overlay_hotkey", ""))
    pause_entry.insert(0, saved_hotkeys.get("pause_hotkey", ""))

    # Save button
    def save_hotkeys():
        existing = load_settings()
        existing["startstop_hotkey"] = startstop_entry.get().strip()
        existing["overlay_hotkey"] = overlay_entry.get().strip()
        existing["pause_hotkey"] = pause_entry.get().strip()
        save_settings(existing)
        hotkey_window.destroy()

    save_btn = ctk.CTkButton(
        hotkey_window,
        text="Save Hotkeys",
        command=save_hotkeys,
        fg_color="#6A1B9A",
        hover_color="#AB47BC",
        text_color="white",
        corner_radius=8
    )
    save_btn.pack(pady=(20, 10))

    # MAIN
def main():
    settings = load_settings()
    start_flask_once()
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

    if user_plan != "free":
        plan_label = ctk.CTkLabel(
            plan_wrapper,
            text=f"{user_plan.title()} Version",
            text_color=plan_colors.get(user_plan, "gray"),
            font=("Helvetica", 12, "italic"),
            fg_color="transparent"
        )
        plan_label.pack(padx=0, pady=2)

    ctk.CTkLabel(frame, text="🎙️ Streamsub", font=("Helvetica", 16, "bold")).pack(pady=(0, 10))

        # --- Language Selection Based on Plan ---
    if user_plan in ["creator", "free"]:
        available_langs = list(language_options.keys())
    elif user_plan == "studio":
        available_langs = ["🇬🇧 English", "🇫🇷 French", "🇪🇸 Spanish", "🇩🇪 German", "🇮🇹 Italian", "🇵🇹 Portuguese"]

    # Add upgrade hint at the bottom (fake entry)
    upgrade_hint = "🔒 More languages in Creator"
    if user_plan == "studio":
        available_langs.append(upgrade_hint)

    selected_lang = ctk.StringVar(value="🌐 Language")

    def on_lang_select(choice):
        if choice == upgrade_hint:
            selected_lang.set("🌐 Language") 
        else:
            selected_lang.set(choice)

    lang_menu = ctk.CTkOptionMenu(
        frame,
        variable=selected_lang,
        values=available_langs,
        command=on_lang_select,
        fg_color="#6A1B9A",
        button_color="#6A1B9A",
        button_hover_color="#AB47BC",
        text_color="white"
    )
    lang_menu.pack(pady=10)

    copy_btn = ctk.CTkButton(
        frame,
        text="📋 Copy OBS URL",
        command=copy_url,
        fg_color="#6A1B9A",
        hover_color="#AB47BC",
        text_color="white",
        corner_radius=8
    )
    copy_btn.pack(pady=10)
    
    settings_btn = ctk.CTkButton(
        frame,
        text="⚙️ Settings",
        command=show_pro_preferences,
        fg_color="#6A1B9A",
        hover_color="#AB47BC",
        text_color="white",
        corner_radius=8
    )
    settings_btn.pack(pady=10)

    global status_label
    status_label = ctk.CTkLabel(frame, text="", font=("Helvetica", 12))
    status_label.place_forget()  # Keeps it invisible

   # --- Right-aligned Start + Reload (aligned with buttons above) ---
    btn_row = ctk.CTkFrame(frame, fg_color="transparent")
    btn_row.pack(pady=(7, 5), anchor="e", padx=(0, 25))  # anchor to right + padding

    def open_mic_selection():
        mic_window = ctk.CTkToplevel()
        mic_window.title("Select Microphone")
        mic_window.geometry("250x150")
    
        pa = pyaudio.PyAudio()
        mic_dict = {}
        mic_list = []
        
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            mic_dict[info['name']] = i
            mic_list.append(info['name'])
        
        mic_var = ctk.StringVar(value=mic_list[0] if mic_list else "No devices")
        
        mic_menu = ctk.CTkOptionMenu(
            mic_window,
            variable=mic_var,
            values=mic_list,
            fg_color="#6A1B9A",
            button_color="#6A1B9A",
            button_hover_color="#AB47BC",
            text_color="white"
        )
        mic_menu.pack(pady=20)
        
        def save_mic_choice():
            choice_name = mic_var.get()
            choice_index = mic_dict[choice_name]
            settings["mic_index"] = choice_index
            save_settings(settings)
            mic_window.destroy()
            
        save_btn = ctk.CTkButton(
            mic_window,
            text="Save",
            command=save_mic_choice,
            fg_color="#6A1B9A",
            hover_color="#AB47BC",
            text_color="white",
            corner_radius=8
        )
        save_btn.pack(pady=27)
    
    mic_btn = ctk.CTkButton(
        btn_row,
        text="♫",
        command=open_mic_selection,
        width=26,
        height=26,
        fg_color="#6A1B9A",
        hover_color="#AB47BC",
        text_color="white",  # or "black" if Light mode
        font=("Helvetica", 16),
        corner_radius=8
    )
    mic_btn.pack(side="left", padx=(0, 6), pady=(8, 0))

    start_btn = ctk.CTkButton(
        btn_row,
        text="▶️ Start",
        command=toggle_backend,
        width=140,
        height=28,
        fg_color="#6A1B9A",
        hover_color="#AB47BC",
        text_color="white",
        corner_radius=8
    )
    start_btn.pack(side="left", padx=(0, 6))
    
    reload_btn = ctk.CTkButton(
        btn_row,
        text="↻",
        command=restart_server,
        width=26,
        height=26,
        fg_color="#6A1B9A",
        hover_color="#AB47BC",
        text_color="white",
        font=("Helvetica", 23),
        corner_radius=8
    )
    reload_btn.pack(side="left")

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    if user_plan == "free":
        global char_count_label
        char_count_label = ctk.CTkLabel(frame, text="Characters remaining: 250,000", font=("Helvetica", 12))
        char_count_label.pack(pady=(0, 0))
        
    root.mainloop()
    
if __name__ == "__main__":
    main()















































































































































































































































































































































































































































































































































































































































































































































