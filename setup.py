from setuptools import setup

APP = ['main.py']
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'streamsub.icns',
    'packages': [],
    'excludes': ['torch', 'whisper', 'numpy', 'matplotlib', 'unittest'],
}

setup(
    app=APP,
    name='Streamsub',
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)

