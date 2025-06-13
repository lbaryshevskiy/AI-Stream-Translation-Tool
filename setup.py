from setuptools import setup

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    'iconfile': 'streamsub.icns',
    'packages': ['encodings', 'tkinter', 'customtkinter', 'flask', 'flask_socketio', 'whisper'],
    'excludes': [
        'PyQt5', 'PyQt6', 'matplotlib', 'email', 'unittest',
        'PySide2', 'PySide6', 'gi', 'gi.repository', 'cv2',
        'tests', 'PyInstaller', 'pyqtgraph', 'torchvision',
        'numpy.core.tests', 'numpy.random._examples'
    ],
    'includes': ['idna', 'requests'],
    'argv_emulation': True,
}

setup(
    app=APP,
    name='Streamsub',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)

