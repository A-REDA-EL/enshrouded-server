#!/usr/bin/env python3
"""Refuse to launch a missing/unprotected installation, then use upstream init."""

import json
import os
from pathlib import Path
import sys

if __package__:
    from .settings import validate_config
else:
    from settings import validate_config


def check_launch(data):
    with (data / "enshrouded_server.json").open() as stream:
        validate_config(json.load(stream))
    executable = data / "enshrouded_server.exe"
    if not executable.is_file() or executable.stat().st_size == 0:
        raise ValueError("Game binary missing/empty; run server.py install on the host")


if __name__ == "__main__":
    try:
        check_launch(Path("/home/steam/enshrouded"))
    except (OSError, ValueError) as exc:
        print(f"Startup refused: {exc}", file=sys.stderr)
        sys.exit(1)
    os.execv("/home/steam/server/init.sh", ["/home/steam/server/init.sh"])
