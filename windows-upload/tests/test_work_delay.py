"""真实工作响应可要求亚秒等待，不能据此中断已接受的歌曲会话。"""
import base64
from pathlib import Path
import plistlib
import unittest
from unittest.mock import Mock, patch

from prototype.uploader import WindowsSongUploader, SongUploadError


class WorkDelayTests(unittest.TestCase):
    def uploader(self):
        value = WindowsSongUploader.__new__(WindowsSongUploader)
        value.progress = Mock()
        value.common = {'cuid': 'test'}
        value.job = Path('unused')
        value.source = Path('unused.m4a')
        value.state = {'cloud_id': 7, 'complete_received': False, 'audio_uploaded': False,
                       'status': base64.b64encode(plistlib.dumps({'session-id': 'test', 'download-requests-url': 'https://example.test/work'})).decode()}
        value._post = Mock(return_value={'payload': [{'cloud-id': 7, 'actions': [{'action': 'complete'}]}], 'all-work-completed': True})
        value.upload_media_extras = Mock(return_value={'extras_completed': True})
        return value

    @patch('prototype.uploader.save_session')
    @patch('prototype.uploader.time.sleep')
    def test_接受亚秒等待并保守等待至少一秒(self, sleep, save):
        for delay in (0, 1, 751, 776, 1000, 600000):
            with self.subTest(delay=delay):
                value = self.uploader()
                result = value._finish(None, 'test', resume_reply={'payload': [], 'retry-in-ms': delay})
                self.assertTrue(result['completed'])
                self.assertTrue(result['extras_completed'])
                self.assertEqual(sleep.call_args.args[0], max(delay, 1000) / 1000)
                self.assertEqual(value._post.call_args.args[2], 'downloadRequests')

    @patch('prototype.uploader.save_session')
    def test_拒绝非法等待时间且不发起后续请求(self, save):
        for delay in (-1, 600001, True, 1.5, '776'):
            with self.subTest(delay=delay):
                value = self.uploader()
                with self.assertRaises(SongUploadError):
                    value._finish(None, 'test', resume_reply={'payload': [], 'retry-in-ms': delay})
                value._post.assert_not_called()
