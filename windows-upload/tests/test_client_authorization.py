"""验证客户端授权的资料库格式、账号一致性和完整保存前的校验。"""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from contextlib import nullcontext

from prototype.client_authorization import authorize, ClientAuthorizationError, library_persistent_id, make_bundle
from prototype.uploader import WindowsSongUploader


@patch("prototype.client_authorization.exclusive_lock", nullcontext)
class ClientAuthorizationTests(unittest.TestCase):
    def session(self):
        return {"headers": {"X-Token": "test-token", "X-Dsid": "123"},
            "library_identity": {"dsid": "123", "cuid": "test-cuid", "troveid": "test-trove", "itre": 1},
            "upload_configuration": {key: "test" for key in (
                "cloud-library-update-request", "cloud-library-update-check", "cloud-assets-update")}}

    def test_资料库头按小端读取完整持久标识(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Library.musicdb"
            path.write_bytes(b"hfma" + bytes(44) + (0x0123456789ABCDEF).to_bytes(8, "little") + b"ignored")
            self.assertEqual(library_persistent_id(path), "0123456789ABCDEF")
            for data in (b"hfma", b"bad!" + bytes(52), b"hfma" + bytes(52)):
                path.write_bytes(data)
                with self.assertRaises(ClientAuthorizationError):
                    library_persistent_id(path)

    def test_账号与资料库属于同一用户才生成授权包(self):
        session = self.session()
        bundle = make_bundle(session, "0123456789ABCDEF")
        self.assertEqual(bundle["context"]["common"]["cuid"], "test-cuid")
        self.assertEqual(bundle["context"]["persistent-library-id"], "0123456789ABCDEF")
        self.assertEqual(bundle["account"], session)
        self.assertNotIn("update-id", bundle["context"]["common"])
        session["library_identity"]["dsid"] = "456"
        with self.assertRaises(ClientAuthorizationError) as error:
            make_bundle(session, "0123456789ABCDEF")
        self.assertNotIn("test-token", str(error.exception))

    def test_未登录未同步或配置不全时不生成成功结果(self):
        for field in ("token", "identity", "configuration"):
            with self.subTest(field=field):
                session = self.session()
                if field == "token":
                    session["headers"].pop("X-Token")
                elif field == "identity":
                    session["library_identity"].pop("troveid")
                else:
                    session["upload_configuration"].pop("cloud-assets-update")
                with self.assertRaises(ClientAuthorizationError):
                    make_bundle(session, "0123456789ABCDEF")

    def test_读取不完整授权时保留已有密文(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Library.musicdb"
            path.write_bytes(b"hfma" + bytes(44) + (123).to_bytes(8, "little"))
            output = Path(temporary) / "authorization.dpapi"
            output.write_bytes(b"existing-encrypted-session")
            device = Mock()
            device.enumerate_processes.return_value = [SimpleNamespace(name="AMPLibraryAgent.exe", pid=123)]
            session = self.session()
            session["library_identity"]["dsid"] = "different-account"
            with patch.dict("sys.modules", {"frida": SimpleNamespace(get_local_device=lambda: device)}), \
                    patch("prototype.client_authorization.collect_session", return_value=session), \
                    patch("prototype.client_authorization.BUNDLE", output):
                with self.assertRaises(ClientAuthorizationError):
                    authorize(path)
            self.assertEqual(output.read_bytes(), b"existing-encrypted-session")

    @patch("prototype.uploader.load_session")
    def test_上传器只解密一次完整授权包避免账号上下文混用(self, load):
        session = self.session()
        bundle = make_bundle(session, "0123456789ABCDEF")
        load.return_value = bundle
        uploader = WindowsSongUploader("authorization.dpapi", "authorization.dpapi", ".", "ffmpeg.exe")
        self.assertEqual(uploader.account, session)
        self.assertEqual(uploader.context, bundle["context"])
        load.assert_called_once()
