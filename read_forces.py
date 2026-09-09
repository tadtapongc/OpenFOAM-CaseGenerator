#!/usr/bin/env python3
"""RapidFOAM force post-processing. Usage: python3 read_forces.py [--live|--plot|--compare]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rapidfoam.cli import forces_main

forces_main()
