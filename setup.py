from setuptools import setup

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    'iconfile': 'streamsub.icns',
    'packages': ['tkinter'],  # Add other packages as needed
}

setup(
    app=APP,
    name='Streamsub',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
