"""Start MiniDesk:  python src/main.py [show.SHO | project.mdshow]

Same as ``python -m minidesk``; works from any folder.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import PySide6  # noqa: F401
    import numpy  # noqa: F401
except ImportError as e:
    print(f"Missing package: {e.name}. Install the requirements first:\n"
          f"    python -m pip install -r \"{os.path.join(ROOT, 'requirements.txt')}\"")
    sys.exit(1)

from minidesk.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
