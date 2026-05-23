"""Allow running as: python -m cfd_gen"""

import sys
from pathlib import Path

# Add src to path when running directly
src_dir = Path(__file__).resolve().parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from cfd_gen.cli import setup_main

if __name__ == "__main__":
    setup_main()
