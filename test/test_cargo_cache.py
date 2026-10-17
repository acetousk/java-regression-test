import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cargo_cache


class CargoCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / "shared"
        self.environment = {"CARGO_TARGET_DIR": str(self.target)}
        self.metadata = json.dumps({"packages": [
            {"name": "moqui", "source": None}, {"name": "path-addon", "source": None},
            {"name": "registry-dep", "source": "registry+test"},
            {"name": "git-dep", "source": "git+test"}]})
        self.check_output = patch.object(cargo_cache.subprocess, "check_output", return_value=self.metadata)
        self.metadata_mock = self.check_output.start()
        self.addCleanup(self.check_output.stop)
        self.run_patch = patch.object(cargo_cache.subprocess, "run", side_effect=self.fake_cargo)
        self.run = self.run_patch.start()
        self.addCleanup(self.run_patch.stop)

    def fake_cargo(self, command, *, cwd, env, check):
        if command[1] == "build":
            binary = self.target / "debug/moqui"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text(cwd.name)
            binary.chmod(0o755)

    def build(self, name):
        directory = self.root / name
        directory.mkdir(exist_ok=True)
        private = directory / "private/moqui"
        cargo_cache.build(["cargo", "build", "--locked", "-p", "moqui"],
                          directory, self.environment, private)
        return private

    def test_switch_invalidates_only_local_packages_and_preserves_private_binary(self):
        private_a = self.build("a")
        self.build("a")
        self.assertEqual(self.metadata_mock.call_count, 1)
        clean = [call.args[0] for call in self.run.call_args_list if call.args[0][1] == "clean"]
        self.assertEqual(clean, [["cargo", "clean", "-p", "moqui", "-p", "path-addon"]])
        private_b = self.build("b")
        self.build("a")
        self.assertEqual(self.metadata_mock.call_count, 3)
        self.assertIn("--locked", self.metadata_mock.call_args.args[0])
        self.assertEqual(private_a.read_text(), "a")
        self.assertEqual(private_b.read_text(), "b")
        self.assertNotEqual(private_a.stat().st_ino, (self.target / "debug/moqui").stat().st_ino)

    def test_empty_metadata_never_becomes_unqualified_cargo_clean(self):
        self.metadata_mock.return_value = '{"packages": []}'
        with self.assertRaisesRegex(RuntimeError, "no local packages"):
            self.build("a")
        self.run.assert_not_called()

    def test_failed_build_does_not_replace_private_binary(self):
        private = self.build("a")
        self.run.side_effect = subprocess.CalledProcessError(1, "cargo")
        with self.assertRaises(subprocess.CalledProcessError):
            self.build("a")
        self.assertEqual(private.read_text(), "a")
