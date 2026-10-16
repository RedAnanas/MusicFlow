"""授权包导入必须保留原密钥、账号和已有任务。"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prototype.portable_session import EncryptedSessionStore, PortableSessionError

spec = importlib.util.spec_from_file_location('server_authorization_import', Path(__file__).resolve().parents[1] / 'import-server-authorization.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


class AuthorizationTransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.private = self.root / 'server/state'
        self.private.mkdir(parents=True, mode=0o700)
        self.package = self.root / 'package'
        self.package.mkdir(mode=0o700)
        self.source = EncryptedSessionStore(self.package / 'key')
        self.source.create_key()
        self.bundle = {'account': {'headers': {'X-Dsid': 'test-account'}},
                       'context': {'common': {'cuid': 'test-client', 'troveid': 'test-trove'}, 'persistent-library-id': 'test-library'}}
        self.source.save(self.package / 'account', self.bundle)
        self.target_key = self.root / 'server/keys/key'
        self.patches = [patch.object(importer, 'PRIVATE', self.private),
                        patch.object(importer, 'secure_directory', lambda path: Path(path).mkdir(parents=True, exist_ok=True, mode=0o700)),
                        patch.dict(os.environ, {'MUSICFLOW_UPLOAD_KEY_FILE': str(self.target_key)})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def test_import_keeps_ciphertext_and_key(self):
        """原密钥导入后仍可解密，目标不是明文授权。"""
        importer.import_authorization(self.package / 'account', self.package / 'key')
        self.assertEqual(self.target_key.read_bytes(), (self.package / 'key').read_bytes())
        self.assertEqual(EncryptedSessionStore(self.target_key).load(self.private / 'account.mfup'), self.bundle)
        self.assertNotIn(b'test-account', (self.private / 'account.mfup').read_bytes())

    def test_different_key_cannot_replace_existing_state(self):
        """新密钥不能让已存在的协议记录失去解密能力。"""
        importer.import_authorization(self.package / 'account', self.package / 'key')
        previous = self.target_key.read_bytes()
        other = EncryptedSessionStore(self.package / 'other-key')
        other.create_key()
        with self.assertRaises(ValueError):
            importer.import_authorization(self.package / 'account', self.package / 'other-key')
        self.assertEqual(self.target_key.read_bytes(), previous)

    def test_other_account_cannot_replace_bundle(self):
        """同密钥加密的其他账号也不能接管原队列。"""
        importer.import_authorization(self.package / 'account', self.package / 'key')
        prior = (self.private / 'account.mfup').read_bytes()
        self.bundle['account']['headers']['X-Dsid'] = 'other-account'
        self.source.save(self.package / 'account', self.bundle)
        with self.assertRaises(ValueError):
            importer.import_authorization(self.package / 'account', self.package / 'key')
        self.assertEqual((self.private / 'account.mfup').read_bytes(), prior)

    def test_tampered_bundle_creates_no_authorization(self):
        """损坏的传输包不能变成服务端已授权状态。"""
        data = bytearray((self.package / 'account').read_bytes())
        data[-1] ^= 1
        (self.package / 'account').write_bytes(data)
        with self.assertRaises(PortableSessionError):
            importer.import_authorization(self.package / 'account', self.package / 'key')
        self.assertFalse(self.target_key.exists())
        self.assertFalse((self.private / 'account.mfup').exists())
