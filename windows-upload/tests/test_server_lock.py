"""Linux 上传互斥锁的跨进程边界。"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import runtime


@unittest.skipIf(os.name == 'nt', 'Linux flock 实测')
class ServerLockTests(unittest.TestCase):
    def test_lock_excludes_other_process_and_releases(self):
        """另一进程不能同时上传，退出后可重新取得锁。"""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            environment = {**os.environ, 'MUSICFLOW_UPLOAD_PRIVATE_DIR': str(directory),
                           'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
            command = [sys.executable, '-c', 'from runtime import exclusive_lock\nwith exclusive_lock():\n    pass\n']
            with patch.object(runtime, 'PRIVATE', directory):
                with runtime.exclusive_lock():
                    blocked = subprocess.run(command, env=environment, capture_output=True)
                released = subprocess.run(command, env=environment, capture_output=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn('已有服务端上传进程运行', blocked.stderr.decode())
            self.assertEqual(released.returncode, 0)
