#!/usr/bin/env python3
"""RapidFOAM case setup. Usage: python setup_case.py configs/config.json"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rapidfoam.cli import setup_main

setup_main()
