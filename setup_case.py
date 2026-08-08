#!/usr/bin/env python3
"""Run cfd-gen without installing. Usage: python3 run.py configs/example.json"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from cfd_gen.cli import setup_main

setup_main()
