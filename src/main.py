"""Start MiniDesk:  python src/main.py [show.SHO | project.mdshow]

Same as ``python -m minidesk``; works from any folder. If the Python you started
lacks the required packages, a MiniDesk virtual environment is used automatically
(C:\\venv\\minidesk or .venv in the project folder).
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

VENVS = [os.path.join(ROOT, ".venv"), r"C:\venv\minidesk", os.path.expanduser("~/venv/minidesk")]


def _venv_python():
    for v in VENVS:
        for exe in (os.path.join(v, "Scripts", "python.exe"), os.path.join(v, "bin", "python")):
            if os.path.exists(exe) and os.path.abspath(exe) != os.path.abspath(sys.executable):
                return exe
    return None


try:
    import numpy  # noqa: F401
    import PySide6  # noqa: F401
except ImportError as e:
    exe = None if os.environ.get("MINIDESK_NO_VENV") else _venv_python()
    if exe:
        env = dict(os.environ, MINIDESK_NO_VENV="1")
        sys.exit(subprocess.call([exe, os.path.abspath(__file__), *sys.argv[1:]], env=env))
    print(f"Missing package: {e.name}. Install the requirements first:\n"
          f"    python -m pip install -r \"{os.path.join(ROOT, 'requirements.txt')}\"\n"
          f"(on Windows with the Microsoft Store Python use a venv, see README: "
          f"python -m venv C:\\venv\\minidesk)")
    sys.exit(1)

from minidesk.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
