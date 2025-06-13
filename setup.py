import sys
sys.setrecursionlimit(5000)

from setuptools import setup

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    OPTIONS = {
    'iconfile': 'streamsub.icns',
    'packages': ['encodings', 'tkinter', 'customtkinter', 'flask', 'flask_socketio', 'whisper'],
    'excludes': ['matplotlib', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'qtpy', 'numpy.random._examples', 'numpy.core.tests'],
}


setup(
    app=APP,
    name='Streamsub',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
