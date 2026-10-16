"""上传准备入口的材料校验与脱敏回归。"""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from app.services import apple_upload_setup as setup


class UploadSetupTests(unittest.TestCase):
    def test_错误算法不会覆盖原文件(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'AMPLibraryAgent.exe'
            target.write_bytes(b'original')
            with patch.object(setup, 'binary_directory', return_value=Path(directory)):
                with self.assertRaises(ValueError):
                    setup.install_algorithms({name: b'wrong' for name in setup.EXPECTED})
            self.assertEqual(target.read_bytes(), b'original')

    def test_不接受任意文件名(self):
        with self.assertRaises(ValueError):
            setup.install_algorithms({'../secret': b'x'})

    def test_算法材料全部通过才安装(self):
        import hashlib
        content = {name: name.encode() for name in setup.EXPECTED}
        expected = {name: hashlib.sha256(value).hexdigest() for name, value in content.items()}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(setup, 'EXPECTED', expected), patch.object(setup, 'binary_directory', return_value=Path(directory)):
                setup.install_algorithms(content)
            for name, value in content.items():
                self.assertEqual((Path(directory) / name).read_bytes(), value)

    def test_下载仅包含源码和说明(self):
        with zipfile.ZipFile(io.BytesIO(setup.desktop_tools())) as archive:
            names = archive.namelist()
            self.assertIn('scripts/authorize-client.py', names)
            self.assertIn('start-authorization.cmd', names)
            self.assertIn('scripts/prepare-authorization.ps1', names)
            self.assertIn('export-server-authorization.py', names)
            self.assertIn('scripts/bootstrap-session.js', names)
            self.assertTrue(all(name.endswith(('.py', '.txt', '.js', '.cmd', '.ps1')) for name in names))
            self.assertFalse(any('account' in name or 'store.key' in name for name in names))

    def test_拒绝明文授权(self):
        with patch.object(setup.sys, 'platform', 'linux'):
            with self.assertRaises(ValueError):
                setup.import_account(b'{"token":"private"}', b'x' * 32)



class UploadSetupRouteTests(unittest.TestCase):
    def test_下载包含授权采样脚本(self):
        from app.api.routes.system import upload_desktop_tools
        response = upload_desktop_tools()
        with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
            self.assertIn('scripts/bootstrap-session.js', archive.namelist())

    def test_缺少算法文件不会写盘(self):
        import asyncio
        from fastapi import UploadFile, HTTPException
        from app.api.routes.system import upload_algorithms
        with patch.object(setup, 'install_algorithms') as install:
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(upload_algorithms([UploadFile(io.BytesIO(b'x'), filename='wrong.dll')]))
        self.assertEqual(caught.exception.status_code, 400)
        install.assert_not_called()

    def test_错误授权返回脱敏错误(self):
        import asyncio
        from fastapi import UploadFile, HTTPException
        from app.api.routes.system import upload_authorization
        with patch.object(setup.sys, 'platform', 'linux'):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(upload_authorization(UploadFile(io.BytesIO(b'private-token'), filename='account.mfup')))
        self.assertEqual(caught.exception.status_code, 400)
        self.assertNotIn('private-token', caught.exception.detail)


if __name__ == '__main__':
    unittest.main()
