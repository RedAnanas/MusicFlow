"""可移植会话的保密、完整性与安全恢复边界。"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prototype.portable_session import EncryptedSessionStore, PortableSessionError


class PortableSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.store = EncryptedSessionStore(self.root / 'key')
        self.store.create_key()
        self.path = self.root / 'session'

    def tearDown(self):
        self.directory.cleanup()

    def test_round_trip_and_random_nonce(self):
        """往返恢复中文内容，密文不包含令牌且每次保存不同。"""
        value = {'token': '仅用于测试的虚构令牌', 'requests': [{'state': 'prepared'}]}
        self.store.save(self.path, value)
        first = self.path.read_bytes()
        self.assertNotIn(value['token'].encode(), first)
        self.assertEqual(self.store.load(self.path), value)
        self.store.save(self.path, value)
        self.assertNotEqual(first, self.path.read_bytes())

    def test_tamper_and_wrong_key_fail(self):
        """篡改密文或换钥时明确失败，不返回空任务。"""
        self.store.save(self.path, {'completed': False})
        second = EncryptedSessionStore(self.root / 'other-key')
        second.create_key()
        with self.assertRaises(PortableSessionError):
            second.load(self.path)
        raw = bytearray(self.path.read_bytes())
        raw[-1] ^= 1
        self.path.write_bytes(raw)
        with self.assertRaises(PortableSessionError):
            self.store.load(self.path)

    def test_existing_key_is_not_replaced(self):
        """初始化不能覆盖已有密钥而导致旧授权不可恢复。"""
        original = self.store.key_path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.store.create_key()
        self.assertEqual(self.store.key_path.read_bytes(), original)

    @unittest.skipIf(os.name == 'nt', 'Linux 文件权限边界')
    def test_insecure_key_permissions_fail(self):
        """共享可读密钥不能用于加载或保存授权。"""
        self.store.key_path.chmod(0o644)
        with self.assertRaises(PortableSessionError):
            self.store.save(self.path, {'completed': False})

    @unittest.skipIf(os.name == 'nt', 'Linux 符号链接边界')
    def test_symlink_session_fails(self):
        """拒绝符号链接，保留链接目标文件。"""
        target = self.root / 'original'
        target.write_bytes(b'keep')
        self.path.symlink_to(target)
        with self.assertRaises(PortableSessionError):
            self.store.save(self.path, {})
        with self.assertRaises(PortableSessionError):
            self.store.load(self.path)
        self.assertEqual(target.read_bytes(), b'keep')

    @unittest.skipIf(os.name == 'nt', 'Linux 协议存储接入')
    def test_protocol_storage_restores_without_windows(self):
        """协议层保存后由新存储实例恢复，不调用 DPAPI。"""
        from prototype.local_session import load_session, save_session
        with patch.dict(os.environ, {'MUSICFLOW_UPLOAD_KEY_FILE': str(self.store.key_path)}):
            save_session(self.path, {'completed': True, 'requests': []})
            self.assertEqual(load_session(self.path), {'completed': True, 'requests': []})

    @unittest.skipIf(os.name == 'nt', 'Linux 协议存储接入')
    def test_missing_server_key_stops(self):
        """缺失密钥时不能写明文或创建新密钥。"""
        from prototype.local_session import save_session, SessionError
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SessionError):
                save_session(self.path, {})
        self.assertFalse(self.path.exists())
