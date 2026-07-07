"""Pytest config: put the repo root on sys.path so tests can import the
top-level `app` and `wayback` modules regardless of pytest's import mode."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
