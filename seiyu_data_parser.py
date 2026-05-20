#!/usr/bin/env python3
# seiyu_data_parser.py - project root entrypoint that ensures src/ is on sys.path

import os
import sys

ROOT = os.path.dirname(__file__)
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from seiyu_data_parser.cli import main

if __name__ == "__main__":
    main()