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
    def test_会话锁等待前一进程结束后才允许下一首提交(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            environment = {**os.environ, 'MUSICFLOW_UPLOAD_PRIVATE_DIR': str(directory),
                           'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
            code = ('import time\nfrom runtime import exclusive_lock\n'
                    'def wait():\n print("waiting", flush=True)\n time.sleep(0.02)\n'
                    'with exclusive_lock("apple-session.lock", wait=wait):\n print("acquired", flush=True)\n')
            child = None
            try:
                with patch.object(runtime, 'PRIVATE', directory), runtime.exclusive_lock('apple-session.lock'):
                    child = subprocess.Popen([sys.executable, '-c', code], env=environment,
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.assertEqual(child.stdout.readline().strip(), 'waiting')
                    self.assertIsNone(child.poll())
                output, error = child.communicate(timeout=5)
                self.assertEqual(child.returncode, 0, error)
                self.assertIn('acquired', output)
            finally:
                if child is not None and child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)

    def test_等待会话锁时可以取消且不取得锁(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.object(runtime, 'PRIVATE', directory), runtime.exclusive_lock('apple-session.lock'):
                def cancel():
                    raise InterruptedError('用户停止等待')

                with self.assertRaises(InterruptedError):
                    with runtime.exclusive_lock('apple-session.lock', wait=cancel):
                        self.fail('等待期间不得进入上传会话')

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

    def test_调度器释放自身引用后子进程仍阻止授权覆盖(self):
        """验证实际继承的 flock，而非仅模拟锁状态。"""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            environment = {**os.environ, 'MUSICFLOW_UPLOAD_PRIVATE_DIR': str(directory),
                           'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
            probe = [sys.executable, '-c', 'from runtime import exclusive_lock\nwith exclusive_lock():\n    pass\n']
            child = None
            try:
                with patch.object(runtime, 'PRIVATE', directory):
                    with runtime.exclusive_lock() as lock:
                        child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'],
                                                 stdin=subprocess.PIPE, pass_fds=(lock.fileno(),), env=environment)
                    blocked = subprocess.run(probe, env=environment, capture_output=True)
                    self.assertNotEqual(blocked.returncode, 0)
                child.communicate(timeout=5)
                released = subprocess.run(probe, env=environment, capture_output=True)
                self.assertEqual(released.returncode, 0)
            finally:
                if child is not None and child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
