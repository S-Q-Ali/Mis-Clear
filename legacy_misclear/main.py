import os
import sys

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import run  # noqa: E402


if __name__ == "__main__":
    run()
