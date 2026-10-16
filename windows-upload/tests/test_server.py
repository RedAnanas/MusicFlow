"""验证同容器身份初始化不会覆盖已有绑定或泄漏令牌。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import server


class ServerBindingTests(unittest.TestCase):
    def test_first_boot_saves_internal_identity(self):
        """首次启动仅建立同容器身份，不要求外部电脑配对。"""
        service = Mock()
        service.bind_worker.side_effect = lambda save: save({'worker_id': 'worker', 'account_scope': 'scope', 'token': 'test-token'})
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'PRIVATE', Path(directory)), patch.object(server, 'save_session') as save:
            binding = server.server_binding(service)
        self.assertEqual(binding['url'], 'http://127.0.0.1:8082')
        self.assertEqual(binding['worker_id'], 'worker')
        save.assert_called_once()

    def test_existing_identity_is_reused(self):
        """重启时复用原身份，不新增或替换队列作用域。"""
        binding = {'worker_id': 'worker', 'account_scope': 'scope', 'token': 'test-token'}
        service = Mock()
        service.worker_status.return_value = {'bound': True, 'worker_id': 'worker', 'account_scope': 'scope'}
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'musicflow-binding.dpapi').touch()
            with patch.object(server, 'PRIVATE', Path(directory)), patch.object(server, 'load_session', return_value=binding):
                self.assertEqual(server.server_binding(service), binding)
        service.bind_worker.assert_not_called()

    def test_mismatched_database_stops(self):
        """数据库与持久身份不一致时停止，不清空任一记录。"""
        service = Mock()
        service.worker_status.return_value = {'bound': True, 'worker_id': 'other', 'account_scope': 'scope'}
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'musicflow-binding.dpapi').touch()
            with patch.object(server, 'PRIVATE', Path(directory)), patch.object(server, 'load_session', return_value={'worker_id': 'worker', 'account_scope': 'scope'}):
                with self.assertRaises(RuntimeError):
                    server.server_binding(service)
        service.bind_worker.assert_not_called()
