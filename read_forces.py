#!/usr/bin/env python3
"""Run force post-processing without installing. Usage: python3 run_forces.py [--live|--plot|--compare]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from cfd_gen.cli import forces_main

forces_main()
