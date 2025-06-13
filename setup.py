from setuptools import setup

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    'iconfile': 'streamsub.icns',
    'packages': ['encodings', 'tkinter', 'customtkinter', 'flask', 'flask_socketio', 'whisper'],
    'excludes': [
        'matplotlib', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'qtpy',
        'PyInstaller', 'gi', 'gi.repository', 'PyGObject',
        'cv2', 'email', 'unittest', 'numpy.core.tests', 'numpy.random._examples'
    ],
    'argv_emulation': True,
    'includes': ['idna', 'requests'],
}

setup(
    app=APP,
    name='Streamsub',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
