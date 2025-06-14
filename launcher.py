import subprocess
import sys
import os

python_exec = sys.executable
script_path = os.path.join(os.path.dirname(__file__), "main.py")
subprocess.Popen([python_exec, script_path])
