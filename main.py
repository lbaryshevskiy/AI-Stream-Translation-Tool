import threading
import queue
import time
time.sleep(0.5)
import wave
import whisper
import pyaudio
from flask import Flask, render_template
from flask_socketio import SocketIO
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)
import customtkinter as ctk
import json
import os
from googletrans import Translator

SETTINGS_FILE = "settings.json"
is_in_settings = False
flask_thread = None

# --- DEVELOPMENT MODE ---
dev_mode = True
dev_override_plan = "studio"  # can be: "free", "studio", "creator"

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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
print(f">>> CONFIRM: async_mode is set to {socketio.async_mode} ✅")

# --- Flask Web Server ---
@app.route('/')
def overlay():
    return render_template('overlay.html')

@socketio.on('connect')
def test_connect():
    print("✅ Socket connected")
    def emit_hello():
        try:
            socketio.emit("subtitle", {"text": "🔥 Hello from Streamsub!"})
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
                if stop_event.is_set():
                    break
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    frames.append(data)
                except Exception as e:
                    print("⚠️ Mic read error:", e)
                    break
            if frames:
                audio_queue.put(b''.join(frames))
        stream.stop_stream()
        stream.close()
        print("🛑 record_audio() stopped")
    except Exception as e:
        print("❌ Failed to open mic stream:", e)

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
                # Get input language setting from saved config
                settings = load_settings()
                input_choice = settings.get("input_language", "🌐 Auto-detect")
                input_code = language_options.get(input_choice) if input_choice != "🌐 Auto-detect" else None

                # Transcribe with or without input language specified
                if input_code:
                    result = model.transcribe(WAVE_OUTPUT_FILENAME, language=input_code)
                else:
                    result = model.transcribe(WAVE_OUTPUT_FILENAME)
                    
                text = result['text'].strip()
                if text:
                    lang_label = selected_lang.get()
                    lang_code = language_options.get(lang_label)
                    
                    if lang_code:
                        translated = translator.translate(text, dest=lang_code).text
                        print(f"🎙️ {text} → 💬 {translated}")
                        try:
                            socketio.emit('subtitle', {'text': translated})
                        except Exception as e:
                            print(f"⚠️ Failed to emit subtitle: {e}")
                        else:
                            print("⚠️ No valid language selected.")
            except Exception as e:
                print(f"❌ Error in transcription/translation: {e}")


# --- Launch Backend Threads ---
def start_backend():
    global backend_threads
    print("🟢 start_backend() triggered")
    stop_event.clear()

    # Create backend threads
    audio_thread = threading.Thread(target=record_audio, daemon=True)
    transcribe_thread = threading.Thread(target=transcribe_loop, daemon=True)

    backend_threads = [audio_thread, transcribe_thread]

    for t in backend_threads:
        t.start()
        
    start_flask_once()
    
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
    status_label.config(text="✅ Copied to clipboard!")
    
def show_pro_preferences():
    global is_in_settings
    is_in_settings = True
    popup = ctk.CTkToplevel()
    popup.title("Settings")
    popup.geometry("430x480")

    from __main__ import dev_mode, dev_override_plan
    user_plan = dev_override_plan if dev_mode else "free"


    tabview = ctk.CTkTabview(popup, width=360, height=300)
    tabview.pack(padx=10, pady=10, fill="both", expand=True)

    tabview.add("Studio")
    tabview.add("Creator")

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

        font_slider = ctk.CTkSlider(page1, from_=12, to=48, number_of_steps=36, command=update_font_size)
        font_slider.set(saved_size)

        settings = load_settings()
        saved_size = settings.get("font_size", 20)
        if isinstance(saved_size, list):  # due to prior tuple saving
            saved_size = saved_size[0]

        font_slider.pack(pady=(0, 8))

        # --- Opacity ---
        opacity_label = ctk.CTkLabel(page1, text="Overlay Opacity:", font=label_font)
        opacity_label.pack(pady=(5, 0))

        opacity_value_label = ctk.CTkLabel(page1, text=f"{saved_opacity:.2f}")
        opacity_value_label.pack(pady=(0, 2))

        overlay_opacity_slider = ctk.CTkSlider(page1, from_=0.1, to=1.0, number_of_steps=18)
        
        saved_opacity = settings.get("opacity", 0.1)
        if isinstance(saved_opacity, list):
            saved_opacity = saved_opacity[0]
        overlay_opacity_slider.set(saved_opacity)
        
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

        # --- Font Color Section ---
        color_label_frame = ctk.CTkFrame(page1, fg_color="transparent")
        color_label_frame.pack(pady=(10, 0))

        font_color_label = ctk.CTkLabel(color_label_frame, text="Font Color:", font=label_font)
        font_color_label.pack(side="left", pady=(0, 0))

        tooltip_icon = ctk.CTkLabel(color_label_frame, text="?", font=("Helvetica", 12, "bold"), width=12)
        tooltip_icon.pack(side="left", padx=(2, 0))
        tooltip_icon.bind("<Enter>", show_tooltip)
        tooltip_icon.bind("<Leave>", hide_tooltip)

        color_menu = ctk.CTkOptionMenu(page1, values=["White", "Yellow", "Cyan", "Green"])
        color_menu.set("White")
        color_menu.configure(state="disabled")
        color_menu.pack(pady=(0, 10))
        
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
                font=(font_family_var.get(), int(font_slider.get())),
                text_color=font_color
            )

            opacity = overlay_opacity_slider.get()
            if opacity <= 0.11:
                preview_frame.configure(fg_color="transparent")
            else:
                shade = int(26 + (opacity * 230))
                hex_color = f"#{shade:02x}{shade:02x}{shade:02x}"
                preview_frame.configure(fg_color=hex_color)

            if not is_in_settings:
                socketio.emit("style_update", {
                    "font": font_family_var.get(),
                    "size": int(font_slider.get()),
                    "opacity": opacity,
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
            
            next_btn.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)
            next_btn.update_idletasks()

        input_lang_label = ctk.CTkLabel(page1, text="Input Language:", font=label_font)
        input_lang_label.pack(pady=(25, 0))

        saved_input_lang = settings.get("input_language", "🌐 Auto-detect")
        input_lang_var = ctk.StringVar(value=saved_input_lang)

        input_lang_menu = ctk.CTkOptionMenu(
            page1,
            variable=input_lang_var,
            values=["🌐 Auto-detect"] + list(language_options.keys())
        )
        input_lang_menu.pack(pady=(0, 12))

        back_btn.place_forget()

        next_btn = ctk.CTkButton(
            studio_tab,
            text="→",
            width=30,
            height=25,
            corner_radius=6,
            command=go_to_page2,
            fg_color="transparent",
            hover_color="#333333",
        )
        next_btn.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)
        next_btn.update_idletasks()

        back_btn = ctk.CTkButton(
            studio_tab,
            text="←",
            width=30,
            height=25,
            corner_radius=6,
            command=go_to_page1,
            fg_color="transparent",
            hover_color="#333333",
        )
        back_btn.place(relx=0.0, rely=1.0, anchor="sw", x=10, y=-10)
        next_btn.update_idletasks()

        back_btn.place_forget()

        arrow_color = "black" if ctk.get_appearance_mode() == "Light" else "white"

        next_btn.configure(text_color=arrow_color)
        back_btn.configure(text_color=arrow_color)


        # --- Page 2: Box Size Selector ---

        def update_box_size(choice):
            if choice == "Custom...":
                width_entry.delete(0, ctk.END)  # Fix here
                custom_frame.pack(pady=(5, 10))
            else:
                custom_frame.pack_forget()

        box_size_label = ctk.CTkLabel(page2, text="Subtitle Box Size:", font=label_font)
        box_size_label.pack(pady=(15, 0))

        box_size_presets = {
            "Compact (600x100)": 600,
            "Wide (800x100)": 800,
            "Tall (600x300)": 600,
            "Full Width (1000x150)": 1000,
            "Custom...": None
        }

        settings = load_settings()
        saved_wrap = settings.get("wraplength", 1000)
        saved_box = settings.get("box_size", "Full Width (1000x150)")
        
        box_size_var = ctk.StringVar(value=saved_box)

        box_size_menu = ctk.CTkOptionMenu(page2, variable=box_size_var, values=list(box_size_presets.keys()), command=update_box_size)
        box_size_menu.pack(pady=(0, 5))

        custom_frame = ctk.CTkFrame(page2, fg_color="transparent")

        width_entry = ctk.CTkEntry(custom_frame, placeholder_text="Width", width=80)
        width_entry.pack(side="left", padx=(0, 5))

        apply_btn = ctk.CTkButton(custom_frame, text="Apply", width=60, command=lambda: apply_custom_width())
        apply_btn.pack(side="left")

        # --- Font Family Selector ---
        font_choices = ["Helvetica", "Arial", "Roboto", "Georgia", "Courier New", "Times New Roman"]
        
        saved_font = load_settings().get("font_family")
        if saved_font in font_choices:
            font_family_var.set(saved_font)

        def update_font_family(choice):
            preview_label.configure(font=(choice, int(font_slider.get())))
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

        # --- Preview Box (moved from page1 to page2) ---
        preview_frame = ctk.CTkFrame(page2, fg_color="transparent", corner_radius=10, width=500, height=150)
        preview_frame.pack(pady=(80, 30), padx=40)
        update_preview()
        
        preview_label = ctk.CTkLabel(
            preview_frame,
            text="This is how your subtitle looks.",
            font=(font_family_var.get(), int(font_slider.get())),
             width=600,
            wraplength=600,
            anchor="center",
            justify="center"
        )
        preview_label.pack(expand=True, fill="both")
    
        if "Custom" in saved_box:
            last_custom = settings.get("last_custom_box_size", f"{saved_wrap}x100")
            box_size_var.set(f"Custom ({last_custom})")
            width_entry.insert(0, last_custom)
            custom_frame.pack(pady=(5, 10))
        else:
            box_size_var.set(saved_box)
        
        def update_opacity(value):
            opacity_value_label.configure(text=f"{float(value):.2f}")
            update_preview()

        overlay_opacity_slider.configure(command=update_opacity)
        update_preview()

        def update_box_size(choice):
            if choice == "Custom...":
                width_entry.delete(0, ctk.END)
                custom_frame.pack(pady=(5, 10))
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

                save_settings({"last_custom_box_size": value})
                box_size_var.set(f"Custom ({value})")
                custom_frame.pack_forget()

            except Exception as e:
                print("Invalid custom size:", e)


    # --- CREATOR TAB ---
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

        right_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        right_frame.pack(side="right", padx=(0, 25))

        dark_mode_switch = ctk.CTkSwitch(right_frame, text="Dark Mode", command=toggle_dark_mode)

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
            font_size = int(font_slider.get())
            opacity = float(overlay_opacity_slider.get())
            font_family = font_family_var.get()
            
            existing = load_settings()
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
            })

            save_settings(existing)

            # Emit updated style to the overlay stream
            socketio.emit("style_update", {
                "font": font_family,
                "size": font_size,
                "opacity": opacity,
                "wraplength": wraplength
            })
                
            global is_in_settings
            is_in_settings = False
            popup.destroy()


        save_btn = ctk.CTkButton(
            right_frame,
            text="Save & Close",
            command=save_and_close,
            width=140
        )
        save_btn.pack(side="right", padx=10, pady=10)
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
    if user_plan == "creator":
        available_langs = list(language_options.keys())
    elif user_plan == "studio":
        available_langs = ["🇬🇧 English", "🇫🇷 French", "🇪🇸 Spanish", "🇩🇪 German", "🇮🇹 Italian"]
    else:  # free
        available_langs = ["🇬🇧 English", "🇫🇷 French", "🇪🇸 Spanish"]

    # Add upgrade hint at the bottom (fake entry)
    upgrade_hint = "🔓 More languages in Creator"
    if user_plan != "creator":
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
        command=on_lang_select
    )
    lang_menu.pack(pady=10)

    copy_btn = ctk.CTkButton(frame, text="📋 Copy OBS URL", command=copy_url)
    copy_btn.pack(pady=10)

    settings_btn = ctk.CTkButton(frame, text="⚙️ Settings", command=show_pro_preferences)
    settings_btn.pack(pady=10)

    global status_label
    status_label = ctk.CTkLabel(frame, text="", font=("Helvetica", 12))
    status_label.place_forget()  # Keeps it invisible

   # --- Right-aligned Start + Reload (aligned with buttons above) ---
    btn_row = ctk.CTkFrame(frame, fg_color="transparent")
    btn_row.pack(pady=(10, 5), anchor="e", padx=(0, 25))  # anchor to right + padding

    start_btn = ctk.CTkButton(
        btn_row,
        text="▶️ Start",
        command=toggle_backend,
        width=140,
        height=28
    )
    start_btn.pack(side="left", padx=(0, 6))  # small gap before reload

    reload_btn = ctk.CTkButton(
        btn_row,
        text="↻",
        command=restart_server,
        width=26,
        height=26,
        fg_color="transparent",
        hover_color="gray20",
        text_color="white",
        font=("Helvetica", 23) 
    )
    reload_btn.pack(side="left")
    
    root.mainloop()
    
if __name__ == "__main__":
    main()





