"""Keep installed user data outside application files; retain the development log."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGED = (ROOT / 'runtime/pythonw.exe').is_file()
STATE = Path(os.environ['LOCALAPPDATA']) / 'JX05' if PACKAGED else ROOT / '.jx05-monitor'
