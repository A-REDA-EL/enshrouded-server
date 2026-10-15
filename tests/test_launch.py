from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from server import Manager
from scripts import launch
from scripts.launch import check_launch


class LaunchTests(unittest.TestCase):
    def test_direct_compose_start_fails_closed_without_private_config(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            with self.assertRaises((OSError, ValueError)):
                check_launch(data)
            (data / "enshrouded_server.exe").write_bytes(b"binary")
            (data / "enshrouded_server.json").write_text('{}')
            with self.assertRaises(ValueError):
                check_launch(data)

    def test_valid_config_and_downloaded_executable_allow_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = Manager(temp)
            with redirect_stdout(io.StringIO()):
                manager.setup()
            with self.assertRaises(ValueError):
                check_launch(manager.data)
            executable = manager.data / "enshrouded_server.exe"
            executable.write_bytes(b"binary")
            check_launch(manager.data)
            config_file = manager.data / "enshrouded_server.json"
            config = json.loads(config_file.read_text())
            config["userGroups"][0]["password"] = ""
            config_file.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                check_launch(manager.data)


class SteamClientTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.client = Path(temporary.name) / "steamclient.so"
        self.client.write_bytes(b"SteamUtils010\0")

    def test_old_bundled_client_is_refreshed_before_launch(self):
        def update(*args, **kwargs):
            self.assertEqual(args[0], ["su", "steam", "-s", "/bin/sh", "-c",
                                      "/home/steam/steamcmd/steamcmd.sh +quit"])
            self.assertTrue(kwargs["check"])
            self.client.write_bytes(b"SteamUtils010\0SteamUtils011\0")

        with patch.object(launch.subprocess, "run", side_effect=update):
            launch.prepare_steam_client(self.client)

    def test_compatible_client_does_not_need_another_download(self):
        self.client.write_bytes(b"SteamUtils010\0SteamUtils011\0")
        with patch.object(launch.subprocess, "run") as update:
            launch.prepare_steam_client(self.client)
        update.assert_not_called()

    def test_successful_command_with_incompatible_client_still_refuses_launch(self):
        with patch.object(launch.subprocess, "run"):
            with self.assertRaisesRegex(ValueError, "SteamUtils011"):
                launch.prepare_steam_client(self.client)

    def test_failed_steam_refresh_refuses_launch(self):
        failure = subprocess.CalledProcessError(1, "steamcmd")
        with patch.object(launch.subprocess, "run", side_effect=failure):
            with self.assertRaises(subprocess.CalledProcessError):
                launch.prepare_steam_client(self.client)
