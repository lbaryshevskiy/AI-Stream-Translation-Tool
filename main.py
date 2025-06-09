import tkinter as tk
import subprocess
import threading
import sys
import os

# Start backend server (Flask + transcription)
def start_backend():
    def run():
        if getattr(sys, 'frozen', False):
            python_exec = sys.executable
        else:
            python_exec = sys.executable
        subprocess.call([python_exec, "backend.py"])
    threading.Thread(target=run, daemon=True).start()

# Copy localhost URL to clipboard
def copy_url():
    root.clipboard_clear()
    root.clipboard_append("http://localhost:5100")
    status_label.config(text="✅ Copied to clipboard!")

# --- GUI Setup ---
root = tk.Tk()
root.title("Live Subtitle Streamer Tool")
root.geometry("420x220")
root.resizable(False, False)

frame = tk.Frame(root, padx=20, pady=20)
frame.pack()

tk.Label(frame, text="🎙️ Real-Time Subtitle Overlay", font=("Helvetica", 16)).pack(pady=(0, 10))
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
