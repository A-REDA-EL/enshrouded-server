#!/usr/bin/env python3
"""Manage a private Enshrouded Compose server. Run on the Linux host with sudo."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import gzip
import json
import os
from pathlib import Path, PurePosixPath
import platform
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile

CONFIG = "enshrouded_server.json"
from scripts.settings import SAVE_PATH, validate_config


def validate_archive(path):
    """Fully read an archive before allowing it to replace any live files."""
    # tarfile can stop at TAR's end marker before gzip checks the CRC/footer.
    expanded = 0
    with gzip.open(path, "rb") as stream:
        while chunk := stream.read(1024**2):
            expanded += len(chunk)
            if expanded > 11 * 1024**3:
                raise ValueError("Expanded archive exceeds the safety limit")
    names = set()
    config = None
    total_size = 0
    with tarfile.open(path, "r:gz") as bundle:
        for member in bundle:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts or "\\" in member.name
                    or member.name in names or not (member.isdir() or member.isfile())
                    or not name.parts or name.parts[0] not in (CONFIG, "saves")
                    or (name.parts[0] == CONFIG and (len(name.parts) != 1 or not member.isfile()))):
                raise ValueError(f"Unsafe backup entry: {member.name}")
            names.add(member.name)
            total_size += member.size
            if total_size > 10 * 1024**3 or len(names) > 100000:
                raise ValueError("Backup exceeds safety limits (10 GiB / 100,000 entries)")
            if member.isfile():
                with bundle.extractfile(member) as stream:
                    if member.name == CONFIG:
                        if member.size > 1024**2:
                            raise ValueError("Configuration is unexpectedly large")
                        config = json.load(stream)
                    else:
                        while stream.read(1024**2):
                            pass
    if config is None:
        raise ValueError("Backup is missing its server configuration")
    validate_config(config)


class Manager:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.data = self.root / "server-data"
        self.backups = self.root / "backups"

    def compose(self, *args, capture=False):
        result = subprocess.run(
            ["docker", "compose", "--project-directory", str(self.root),
             "-f", str(self.root / "compose.yaml"), *args],
            check=True, text=True, stdout=subprocess.PIPE if capture else None,
        )
        return result.stdout if capture else ""

    @contextmanager
    def lock(self):
        with (self.root / ".maintenance.lock").open("a") as lockfile:
            try:
                fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another maintenance command is running") from None
            yield

    def setup(self, name="Embervale with Friends", players=8):
        if type(players) is not int or not 1 <= players <= 16:
            raise ValueError("players must be between 1 and 16")
        if not name.strip():
            raise ValueError("Server name cannot be empty")
        self.data.mkdir(mode=0o750, exist_ok=True)
        (self.data / "saves").mkdir(mode=0o750, exist_ok=True)
        self.backups.mkdir(mode=0o700, exist_ok=True)
        path = self.data / CONFIG
        if path.exists():
            self.check_config()
            print("Existing server configuration preserved.")
            return
        credentials = self.root / "credentials.txt"
        if credentials.exists():
            raise ValueError("credentials.txt exists without a server config; recover the old config or move that file first")
        admin, friends = secrets.token_urlsafe(18), secrets.token_urlsafe(18)
        def group(label, password, is_admin):
            return dict(name=label, password=password, canKickBan=is_admin,
                        canAccessInventories=True, canEditWorld=True,
                        canEditBase=True, canExtendBase=True, reservedSlots=0)
        config = dict(name=name, saveDirectory=SAVE_PATH, logDirectory="./logs",
                      ip="0.0.0.0", queryPort=15637, slotCount=players,
                      voiceChatMode="Proximity", enableVoiceChat=False,
                      enableTextChat=True, gameSettingsPreset="Default",
                      userGroups=[group("Admin", admin, True), group("Friends", friends, False)])
        validate_config(config)
        with open(path, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
            json.dump(config, stream, indent=2)
            stream.write("\n")
        with open(credentials, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
            stream.write(f"Admin password: {admin}\nFriends password: {friends}\n")
        print("Private configuration created. Passwords are in credentials.txt (mode 0600).")

    def check_config(self):
        with (self.data / CONFIG).open() as stream:
            validate_config(json.load(stream))

    def preflight(self):
        if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
            raise RuntimeError("Deploy on Linux x86-64. Hetzner CAX/ARM is unsupported.")
        arch = subprocess.check_output(["docker", "info", "--format", "{{.Architecture}}"], text=True).strip()
        if arch not in ("x86_64", "amd64"):
            raise RuntimeError("The Docker daemon must run on x86-64")
        self.compose("config", "--quiet")
        self.check_config()
        if shutil.disk_usage(self.root).free < 30 * 1024**3:
            raise RuntimeError("At least 30 GiB free disk space is required for install/update")
        mem_kib = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                           if line.startswith("MemTotal:")))
        if mem_kib < 15 * 1024**2:
            print("WARNING: 16 GB host RAM is recommended; reduce GAME_MEMORY_LIMIT if needed.", file=sys.stderr)
        if (os.cpu_count() or 0) < 6:
            print("WARNING: Keen recommends 6 fast CPU cores for 4–6 active players.", file=sys.stderr)

    def is_running(self):
        # A crash-looping container can resume at any moment unless explicitly stopped.
        return bool(self.compose("ps", "--status", "running", "--status", "restarting",
                                 "-q", "enshrouded", capture=True).strip())

    def start(self):
        self.check_config()
        if not (self.data / "enshrouded_server.exe").is_file():
            raise RuntimeError("Game files are missing. Run: sudo ./server.py install")
        self.compose("up", "-d", "--wait", "--wait-timeout", "600", "enshrouded")

    def write_archive(self):
        self.check_config()
        for path in [self.data / CONFIG, *(self.data / "saves").rglob("*")]:
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ValueError(f"Unsupported file in world data: {path}")
        if (self.data / "saves").is_symlink():
            raise ValueError("Save directory cannot be a symlink")
        self.backups.mkdir(mode=0o700, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        destination = self.backups / f"enshrouded-{stamp}.tar.gz"
        fd, temporary = tempfile.mkstemp(prefix=".backup-", dir=self.backups)
        os.close(fd)
        try:
            with tarfile.open(temporary, "w:gz") as bundle:
                bundle.add(self.data / CONFIG, arcname=CONFIG)
                bundle.add(self.data / "saves", arcname="saves")
            validate_archive(temporary)
            with open(temporary, "rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        print(f"Verified backup: {destination}")
        return destination

    def backup(self, restart=True, keep=14):
        if keep < 1:
            raise ValueError("Backup retention must be at least 1")
        was_running = self.is_running()
        if was_running:
            self.compose("stop", "enshrouded")
        try:
            archive = self.write_archive()
            archives = sorted(self.backups.glob("enshrouded-*.tar.gz"))
            for old in archives[:-keep]:
                old.unlink()
            # The game's archived logs are separate from Docker's rotated output.
            cutoff = datetime.now(timezone.utc).timestamp() - 14 * 86400
            log_archive = self.data / "logs/backup"
            if log_archive.is_dir() and not log_archive.is_symlink():
                for log in log_archive.iterdir():
                    if log.is_file() and not log.is_symlink() and log.stat().st_mtime < cutoff:
                        log.unlink()
            return archive
        finally:
            if was_running and restart:
                self.compose("up", "-d", "--wait", "--wait-timeout", "600", "enshrouded")

    def update(self):
        self.check_config()
        self.backup(restart=False)
        # A failed updater must never launch a partially updated installation.
        self.compose("run", "--rm", "--no-deps", "updater")
        self.compose("up", "-d", "--wait", "--wait-timeout", "600", "enshrouded")

    def restore(self, archive):
        archive = Path(archive).resolve()
        validate_archive(archive)
        # Stage and validate everything before interrupting the live server.
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=self.root) as temporary:
            stage = Path(temporary)
            with tarfile.open(archive, "r:gz") as bundle:
                for member in bundle:
                    target = stage / member.name
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True, mode=0o750)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
                        with bundle.extractfile(member) as source, target.open("wb") as dest:
                            shutil.copyfileobj(source, dest)
                        target.chmod(0o600)
            (stage / "saves").mkdir(exist_ok=True)
            was_running = self.is_running()
            self.backup(restart=False)
            previous = stage / "previous-saves"
            os.replace(self.data / "saves", previous)
            try:
                os.replace(stage / "saves", self.data / "saves")
                os.replace(stage / CONFIG, self.data / CONFIG)
            except BaseException:
                if (self.data / "saves").exists():
                    shutil.rmtree(self.data / "saves")
                os.replace(previous, self.data / "saves")
                raise
            if was_running:
                self.compose("up", "-d", "--wait", "--wait-timeout", "600", "enshrouded")
        print("World and configuration restored. Passwords now match the restored configuration.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "install", "start", "stop", "restart", "status",
                                           "logs", "check", "backup", "update", "restore"])
    parser.add_argument("archive", nargs="?")
    parser.add_argument("--name", default="Embervale with Friends")
    parser.add_argument("--players", type=int, default=8)
    parser.add_argument("--keep", type=int, default=14)
    parser.add_argument("--yes", action="store_true", help="Confirm replacement of the live world during restore")
    args = parser.parse_args()
    manager = Manager(Path(__file__).resolve().parent)
    try:
        if args.command in ("status", "logs"):
            manager.compose(*(("ps",) if args.command == "status" else ("logs", "--tail", "150", "-f", "enshrouded")))
            return 0
        if platform.system() == "Linux" and os.geteuid() != 0:
            raise RuntimeError("Run maintenance with sudo so archive permissions and ownership are preserved")
        with manager.lock():
            if args.command == "setup":
                manager.setup(args.name, args.players)
            elif args.command == "install":
                manager.setup(args.name, args.players)
                manager.preflight()
                manager.compose("pull", "enshrouded")
                manager.update()
            elif args.command == "check":
                manager.preflight()
                print("Host and configuration checks passed. Public IPv4/firewall still need external verification.")
            elif args.command == "start":
                manager.start()
            elif args.command == "stop":
                manager.compose("stop", "enshrouded")
            elif args.command == "restart":
                manager.check_config()
                manager.compose("restart", "enshrouded")
            elif args.command == "backup":
                manager.backup(keep=args.keep)
            elif args.command == "update":
                manager.preflight()
                manager.update()
            elif args.command == "restore":
                if not args.archive or not args.yes:
                    raise ValueError("Use: sudo ./server.py restore PATH.tar.gz --yes (replaces current world/config)")
                manager.restore(args.archive)
    except (OSError, EOFError, ValueError, RuntimeError, tarfile.TarError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
