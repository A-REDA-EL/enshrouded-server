#!/usr/bin/env python3
"""Validate the installation and Steam client, then use upstream init."""

import json
import os
from pathlib import Path
import subprocess
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


def prepare_steam_client(client=Path("/home/steam/steamcmd/linux64/steamclient.so")):
    # Proton forwards Steamworks calls to this Linux library. The pinned image's
    # older client lacks the interface required by the current game server.
    if client.is_file() and b"SteamUtils011\0" in client.read_bytes():
        return
    print("Refreshing Steam client for SteamUtils011 (game files are unchanged)...", flush=True)
    subprocess.run(["su", "steam", "-s", "/bin/sh", "-c",
                    "/home/steam/steamcmd/steamcmd.sh +quit"], check=True, timeout=240)
    if not client.is_file() or b"SteamUtils011\0" not in client.read_bytes():
        raise ValueError("Updated Steam client still lacks SteamUtils011; refusing to launch")


if __name__ == "__main__":
    try:
        check_launch(Path("/home/steam/enshrouded"))
        prepare_steam_client()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Startup refused: {exc}", file=sys.stderr)
        sys.exit(1)
    os.execv("/home/steam/server/init.sh", ["/home/steam/server/init.sh"])
