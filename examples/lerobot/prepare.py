#!/usr/bin/env python3
"""Import a LeRobot Dataset v3 repository through HFlow's public CLI."""

import sys

from hflow.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["import", "lerobot", *sys.argv[1:]]))
