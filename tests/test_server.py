import io
from contextlib import redirect_stdout
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from server import Manager, validate_config, validate_archive


class LocalManager(Manager):
    """Simulate only the unavailable Docker boundary; use real files/archives."""

    def __init__(self, root):
        super().__init__(root)
        self.running = True
        self.calls = []
        self.fail_download = False

    def is_running(self):
        return self.running

    def compose(self, *args, capture=False):
        self.calls.append(args)
        if args[0] == "stop":
            self.running = False
        elif args[0] == "up":
            self.running = True
        elif args[0] == "run" and self.fail_download:
            raise RuntimeError("download failed")
        return ""


class ServerTests(unittest.TestCase):
    def setUp(self):
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = LocalManager(self.root)
        self.manager.setup("Friends' world", 8)
        self.config = self.root / "server-data/enshrouded_server.json"
        self.saves = self.root / "server-data/saves"
        (self.saves / "world").write_bytes(b"saved world")

    def test_setup_creates_distinct_private_roles_and_preserves_existing_config(self):
        config = json.loads(self.config.read_text())
        validate_config(config)
        self.assertEqual(config["slotCount"], 8)
        groups = config["userGroups"]
        self.assertEqual(len(groups), 2)
        self.assertNotEqual(groups[0]["password"], groups[1]["password"])
        self.assertTrue(groups[0]["canKickBan"])
        self.assertFalse(groups[1]["canKickBan"])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        before = self.config.read_bytes()
        self.manager.setup("other", 16)
        self.assertEqual(self.config.read_bytes(), before)

    def test_invalid_or_public_config_is_rejected(self):
        for value in (0, 17, True, "8"):
            config = json.loads(self.config.read_text())
            config["slotCount"] = value
            with self.assertRaises(ValueError):
                validate_config(config)
        config = json.loads(self.config.read_text())
        config["userGroups"][1]["password"] = ""
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_malformed_config_shapes_are_rejected(self):
        for config in ([], None, {"slotCount": 8, "ip": "0.0.0.0", "queryPort": 15637,
                                  "saveDirectory": "/home/steam/enshrouded/saves", "userGroups": [None]}):
            with self.assertRaises(ValueError):
                validate_config(config)

    def test_truncated_archive_is_rejected(self):
        archive = self.manager.backup()
        truncated = self.root / "truncated.tar.gz"
        truncated.write_bytes(archive.read_bytes()[:-8])
        with self.assertRaises((ValueError, EOFError, OSError)):
            validate_archive(truncated)

    def test_existing_credentials_do_not_allow_a_mismatched_new_config(self):
        self.config.unlink()
        with self.assertRaises(ValueError):
            self.manager.setup()
        self.assertFalse(self.config.exists())

    def test_maintenance_lock_rejects_overlapping_commands(self):
        other = Manager(self.root)
        with self.manager.lock():
            with self.assertRaises(RuntimeError):
                with other.lock():
                    self.fail("Second operation acquired the same lock")

    def test_restart_loop_is_stopped_before_world_files_are_archived(self):
        manager = Manager(self.root)
        state = {"value": "restarting"}

        def compose(*args, capture=False):
            if args[0] == "ps":
                return "container-id" if state["value"] in args else ""
            if args[0] == "stop":
                state["value"] = "exited"
            if args[0] == "up":
                state["value"] = "running"
            return ""

        original = manager.write_archive
        def write_archive():
            self.assertEqual(state["value"], "exited", "Restart loop can race the archive")
            return original()

        with patch.object(manager, "compose", side_effect=compose), patch.object(manager, "write_archive", side_effect=write_archive):
            manager.backup()
        self.assertEqual(state["value"], "running")

    def test_backup_is_complete_private_and_restarts_previously_running_server(self):
        archive = self.manager.backup()
        self.assertTrue(self.manager.running)
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        with tarfile.open(archive) as bundle:
            self.assertEqual(bundle.extractfile("saves/world").read(), b"saved world")
            self.assertIn("enshrouded_server.json", bundle.getnames())
        self.assertEqual(self.manager.calls[0][0], "stop")
        self.assertEqual(self.manager.calls[-1][0], "up")

    def test_backup_error_restarts_server_without_publishing_partial_archive(self):
        with patch.object(self.manager, "write_archive", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.manager.backup()
        self.assertTrue(self.manager.running)
        self.assertEqual(list((self.root / "backups").glob("*.tar.gz")), [])

    def test_backup_does_not_start_a_stopped_server(self):
        self.manager.running = False
        self.manager.backup()
        self.assertFalse(self.manager.running)
        self.assertEqual(self.manager.calls, [])

    def test_update_failure_keeps_server_stopped_with_recovery_backup(self):
        self.manager.fail_download = True
        with self.assertRaises(RuntimeError):
            self.manager.update()
        self.assertFalse(self.manager.running)
        self.assertEqual(len(list((self.root / "backups").glob("*.tar.gz"))), 1)

    def test_restore_preserves_current_world_before_replacing_it(self):
        archive = self.manager.backup()
        (self.saves / "world").write_bytes(b"new world")
        (self.saves / "extra").write_bytes(b"must disappear")
        self.manager.restore(archive)
        self.assertEqual((self.saves / "world").read_bytes(), b"saved world")
        self.assertFalse((self.saves / "extra").exists())
        self.assertTrue(self.manager.running)
        archives = list((self.root / "backups").glob("*.tar.gz"))
        self.assertGreaterEqual(len(archives), 2)
        worlds = []
        for path in archives:
            with tarfile.open(path) as bundle:
                worlds.append(bundle.extractfile("saves/world").read())
        self.assertIn(b"new world", worlds)

    def test_retention_keeps_requested_number_of_verified_backups(self):
        for _ in range(4):
            self.manager.backup(keep=2)
        self.assertEqual(len(list((self.root / "backups").glob("*.tar.gz"))), 2)

    def test_symlinks_in_save_directory_are_rejected(self):
        (self.saves / "link").symlink_to(self.config)
        with self.assertRaises(ValueError):
            self.manager.backup()
        self.assertTrue(self.manager.running)

    def test_restore_rejects_traversal_links_and_missing_config_before_stopping(self):
        for name, link in (("../escape", False), ("saves/link", True), ("saves/world", False)):
            archive = self.root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                entry = tarfile.TarInfo(name)
                if link:
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = "/etc/passwd"
                    bundle.addfile(entry)
                else:
                    entry.size = 3
                    bundle.addfile(entry, io.BytesIO(b"bad"))
            with self.assertRaises(ValueError):
                self.manager.restore(archive)
            self.assertTrue(self.manager.running)


if __name__ == "__main__":
    unittest.main()
