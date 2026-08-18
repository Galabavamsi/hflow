"""Shared test setup.

Pins the whole suite to the system ffmpeg via the explicit override so tests
never trigger the pinned-build download (a per-machine, network-bound step).
Set at import time, before any test imports resolve the (cached) binary path.
"""

import os
import shutil

_system_ffmpeg = shutil.which("ffmpeg")
if _system_ffmpeg is not None:
    os.environ.setdefault("HFLOW_FFMPEG", _system_ffmpeg)
