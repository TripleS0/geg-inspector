"""Tests for runtime path resolution across dev and env override."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path


class RuntimePathsTests(unittest.TestCase):
    """Cover env overrides and folder creation."""

    def setUp(self) -> None:
        self._old_env = {
            "DATAFUSIONX_HOME": os.environ.pop("DATAFUSIONX_HOME", None),
            "DATAFUSIONX_DB_PATH": os.environ.pop("DATAFUSIONX_DB_PATH", None),
        }
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        from app import runtime_paths as rp
        importlib.reload(rp)
        self._rp = rp

    def tearDown(self) -> None:
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        importlib.reload(self._rp)

    def test_default_db_path_uses_data_dir(self) -> None:
        path = self._rp.default_db_path()
        self.assertTrue(path.parent.exists(), "data dir should be created")
        self.assertEqual(path.name, "datafusionx.sqlite3")

    def test_home_override_redirects_data_dir(self) -> None:
        os.environ["DATAFUSIONX_HOME"] = self._tmp.name
        importlib.reload(self._rp)
        data = self._rp.data_dir()
        self.assertEqual(data, Path(self._tmp.name).resolve() / "data")
        self.assertTrue(data.is_dir())
        db = self._rp.default_db_path()
        self.assertEqual(db.parent, data)

    def test_db_path_override_takes_priority(self) -> None:
        target = Path(self._tmp.name) / "custom.db"
        os.environ["DATAFUSIONX_DB_PATH"] = str(target)
        importlib.reload(self._rp)
        path = self._rp.default_db_path()
        self.assertEqual(path, target.resolve())
        self.assertTrue(path.parent.exists())


if __name__ == "__main__":
    unittest.main()
