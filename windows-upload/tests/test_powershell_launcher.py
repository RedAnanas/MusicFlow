"""使用实际 Windows PowerShell 验证双击入口，无联网和授权读取。"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.name == 'nt' and shutil.which('powershell.exe'), '仅在 Windows 验证原生启动器')
class PowerShellLauncherTests(unittest.TestCase):
    def test_中文路径和依赖清单可到达安装确认并取消(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='授权工具 空格 ') as directory:
            target = Path(directory)
            (target / 'scripts').mkdir()
            (target / 'prototype').mkdir()
            shutil.copy2(root / 'scripts/prepare-authorization.ps1', target / 'scripts')
            shutil.copy2(root / 'prototype/requirements.txt', target / 'prototype')
            shutil.copy2(root / 'requirements-server.txt', target)
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(target / '.venv')], check=True, capture_output=True)
            command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(target / 'scripts/prepare-authorization.ps1')]
            result = subprocess.run(command, input='N\n', text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=30)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1)
            self.assertNotIn('Traceback', output)
            self.assertIn('Frida', output)
            self.assertFalse((target / 'state/account.mfup').exists())
            script = target / 'scripts/prepare-authorization.ps1'
            script.write_text(script.read_text(encoding='utf-8-sig').replace(
                'import sys, tkinter; assert sys.version_info >= (3,12)',
                "raise RuntimeError(12345)"), encoding='utf-8-sig')
            failure = subprocess.run(command, text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=30)
            self.assertEqual(failure.returncode, 1)
            self.assertIn('RuntimeError: 12345', failure.stdout + failure.stderr)
