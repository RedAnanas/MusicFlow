"""验证一键入口仅在本次读取成功后导出，重新授权保留原密钥。"""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('authorize_window', Path(__file__).resolve().parents[1] / 'scripts/authorize-client.py')
window = importlib.util.module_from_spec(spec)
spec.loader.exec_module(window)


class AuthorizationLauncherTests(unittest.TestCase):
    def test_读取成功后才导出且复用指定密钥(self):
        with patch.object(window, 'authorize') as authorize, patch.object(window.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            window.authorize_and_export('library.musicdb', Path('private output'), Path('original.key'))
        authorize.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[-2:], ['--key-file', 'original.key'])
        self.assertIn('private output', command)
        self.assertIn(str(window.BUNDLE), command)

    def test_读取失败不导出旧授权(self):
        with patch.object(window, 'authorize', side_effect=window.ClientAuthorizationError('读取失败')), patch.object(window.subprocess, 'run') as run:
            with self.assertRaises(window.ClientAuthorizationError):
                window.authorize_and_export(None, 'output')
        run.assert_not_called()

    def test_导出失败不显示成功也不泄露输出(self):
        with patch.object(window, 'authorize'), patch.object(window.subprocess, 'run', return_value=Mock(returncode=1, stderr=b'private-token')):
            with self.assertRaises(window.ClientAuthorizationError) as caught:
                window.authorize_and_export(None, 'output')
        self.assertNotIn('private-token', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
