import pyaudio

pa = pyaudio.PyAudio()
try:
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
    data = stream.read(1024)
    print("✅ Mic read success, length:", len(data))
    stream.close()
except Exception as e:
    print("❌ Mic test failed:", e)
pa.terminate()
