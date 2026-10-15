from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from server import Manager
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
