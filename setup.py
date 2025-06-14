from setuptools import setup

APP = ['main.py']
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'streamsub.icns',
    'packages': ['customtkinter', 'flask', 'flask_socketio', 'whisper'],
    'excludes': ['tkinter.test', 'unittest', 'PyQt5', 'matplotlib'],
}

setup(
    app=APP,
    name='Streamsub',
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
