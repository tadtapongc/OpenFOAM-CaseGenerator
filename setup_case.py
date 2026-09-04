#!/usr/bin/env python3
"""OpenFOAM Case Generator case setup. Usage: python setup_case.py configs/config.json"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from cfd_gen.cli import setup_main

setup_main()
