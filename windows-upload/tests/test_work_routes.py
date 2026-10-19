"""长等待后刷新同一会话路由，保留原曲目和工作序号。"""
import base64
from pathlib import Path
import plistlib
import unittest
from unittest.mock import Mock, patch

from prototype.uploader import WindowsSongUploader, SongUploadError


class WorkRouteTests(unittest.TestCase):
    def uploader(self):
        value = WindowsSongUploader.__new__(WindowsSongUploader)
        value.progress = Mock()
        value.common = {'cuid': 'test'}
        value.account = {'upload_configuration': {'cloud-library-update-check': 'check-existing-update'}}
        value.job, value.source = Path('unused'), Path('unused.m4a')
        self.old = {'session-id': 'same-session', 'download-requests-url': 'old-work', 'upload-responses-url': 'old-results'}
        self.fresh = {**self.old, 'download-requests-url': 'fresh-work', 'upload-responses-url': 'fresh-results', 'additional-fields-url': 'fields'}
        value.state = {'cloud_id': 7, 'complete_received': False, 'audio_uploaded': False, 'sequence_id': 4, 'match_state': 13,
                       'initial': base64.b64encode(plistlib.dumps({'update-id': 'original-update'})).decode(),
                       'status': base64.b64encode(plistlib.dumps(self.old)).decode()}
        value.upload_media_extras = Mock(return_value={'extras_completed': True})
        return value

    @patch('prototype.uploader.save_session')
    @patch('prototype.uploader.time.sleep')
    def test_长等待后用新路由继续同一曲目且不丢序号(self, sleep, save):
        value = self.uploader()
        value._post = Mock(side_effect=[self.fresh,
            {'status': 0, 'all-work-completed': True, 'payload': [{'cloud-id': 7, 'actions': [{'action': 'complete'}]}]}])
        result = value._finish(None, 'same-track', resume_reply={'status': 0, 'retry-in-ms': 180000})
        self.assertTrue(result['completed'])
        sleep.assert_called_once_with(180)
        self.assertEqual(value._post.call_args_list[0].args, ('check-existing-update', {'cuid': 'test', 'update-id': 'original-update'}))
        request = value._post.call_args_list[1]
        self.assertEqual(request.args[0], 'fresh-work')
        self.assertEqual(request.args[1]['sequence-id'], 4)
        self.assertEqual(request.args[1]['session-id'], 'same-session')
        self.assertEqual(value.state['cloud_id'], 7)
        self.assertEqual(plistlib.loads(base64.b64decode(value.state['status'])), self.fresh)

    @patch('prototype.uploader.save_session')
    def test_会话变化时拒绝替换旧路由(self, save):
        value = self.uploader()
        previous = value.state['status']
        value._post = Mock(return_value={**self.fresh, 'session-id': 'another-session'})
        with self.assertRaises(SongUploadError) as caught:
            value._refresh_work_status()
        self.assertEqual(getattr(caught.exception, 'code', None), 'session_changed')
        self.assertEqual(value.state['status'], previous)
        save.assert_not_called()

    @patch('prototype.uploader.save_session')
    @patch('prototype.uploader.time.sleep')
    def test_短等待不额外查询路由(self, sleep, save):
        value = self.uploader()
        value._refresh_work_status = Mock()
        value._post = Mock(return_value={'all-work-completed': True, 'payload': [{'cloud-id': 7, 'actions': [{'action': 'complete'}]}]})
        value._finish(None, 'same-track', resume_reply={'status': 0, 'retry-in-ms': 1000})
        value._refresh_work_status.assert_not_called()
