"""验证密文原子保存，失败时保留旧记录。"""

import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from prototype.local_session import load_session, save_session


@unittest.skipUnless(os.name == 'nt', 'Windows DPAPI 专用回归；Linux 密文由 portable_session 覆盖')
class LocalSessionTests(unittest.TestCase):
    def test_密文可替换并由当前用户读取(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.dpapi"
            save_session(path, {"value": "旧记录"})
            save_session(path, {"value": "新记录"})
            self.assertEqual(load_session(path), {"value": "新记录"})
            self.assertNotIn("新记录".encode(), path.read_bytes())
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_写入或替换失败时保留旧记录并清理临时文件(self):
        for operation in ("os.fsync", "Path.replace"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "session.dpapi"
                path.write_bytes(b"old-encrypted-record")
                with patch("prototype.local_session._crypt", return_value=b"new-encrypted-record"), \
                        patch("prototype.local_session." + operation, side_effect=OSError("模拟保存中断")):
                    with self.assertRaises(OSError):
                        save_session(path, {"completed": True})
                self.assertEqual(path.read_bytes(), b"old-encrypted-record")
                self.assertEqual(list(Path(directory).iterdir()), [path])
