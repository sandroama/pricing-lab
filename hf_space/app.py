"""Hugging Face Spaces entrypoint for pricing-lab.

Runs the project dashboard without requiring `pip install -e .`: the src/
tree goes on sys.path (same pattern as the sibling Spaces in this portfolio),
so requirements.txt only needs third-party packages.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

# Works from hf_space/ inside the project tree AND when copied to the Space
# repo root next to the uploaded project tree.
_HERE = Path(__file__).resolve().parent
ROOT = _HERE if (_HERE / "dashboard").is_dir() else _HERE.parent
sys.path.insert(0, str(ROOT / "src"))

runpy.run_path(str(ROOT / "dashboard" / "app.py"), run_name="__main__")
