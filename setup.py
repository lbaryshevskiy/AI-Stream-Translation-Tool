from setuptools import setup

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    'iconfile': 'streamsub.icns',
    'packages': ['encodings', 'tkinter', 'customtkinter', 'flask', 'flask_socketio', 'whisper'],
    'excludes': ['matplotlib', 'PyQt5', 'PySide2'],
}

setup(
    app=APP,
    name='Streamsub',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
