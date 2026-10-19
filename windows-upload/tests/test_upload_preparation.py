"""使用伪造媒体和算法验证本地准备，不读取授权或发送网络请求。"""

import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from prototype.uploader import WindowsSongUploader


class UploadPreparationTests(unittest.TestCase):
    def make_uploader(self, directory):
        uploader = WindowsSongUploader.__new__(WindowsSongUploader)
        uploader.private = directory
        uploader.ffmpeg = Path('ffmpeg')
        uploader.ffprobe = Path('ffprobe')
        uploader.progress = Mock()
        uploader._post = Mock(return_value={'url': 'https://example.test/?cuid=test&troveid=test'})
        uploader._finish = Mock(return_value={'extras_completed': True})
        uploader.context = {'common': {'cuid': 'test', 'troveid': 'test'}, 'persistent-library-id': 'test', 'itre': b'test'}
        uploader.account = {'upload_configuration': {'cloud-library-update-request': 'https://example.test/'}}
        source = directory / 'song.m4a'
        source.write_bytes(struct.pack('>I4s', 12, b'mdat') + b'AAC!')
        info = {'streams': [{'codec_type': 'audio', 'codec_name': 'aac', 'profile': 'LC',
                             'duration': '120', 'sample_rate': '44100', 'bit_rate': '256000'}],
                'format': {'tags': {'title': '测试歌曲', 'lyrics': '测试歌词'}}}

        def run(command, **kwargs):
            if command[0] == 'ffprobe':
                return Mock(stdout=json.dumps(info).encode(), returncode=0)
            output = Path(command[-1])
            output.write_bytes(source.read_bytes() if output.suffix == '.m4a' else b'\0' * 16)
            return Mock(returncode=0)

        return uploader, source, run

    def test_提前计算不创建会话且上传复用全部本地结果(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            uploader, source, run = self.make_uploader(directory)
            with patch('prototype.uploader.subprocess.run', side_effect=run) as processes, \
                    patch('prototype.uploader.generate_fingerprint', side_effect=lambda pcm, kind, sdk, progress: kind.encode()) as fingerprints, \
                    patch('prototype.uploader.generate_signature', return_value=b'signature') as signature, \
                    patch('prototype.uploader.WindowsSapSigner') as signer:
                uploader.prepare(source, fingerprints=True)
                calls = processes.call_count
                self.assertEqual(calls, 4)
                uploader._post.assert_not_called()
                signer.assert_not_called()
                self.assertFalse(list(directory.glob('upload-*.dpapi')))
                track_id = uploader._prepared_media[2]['persistent-id']
                uploader.upload(source)
                for kind in ('partial', 'full-lowres', 'signature'):
                    self.assertEqual(uploader._fingerprint(kind), kind.encode())
                uploader.prepare_extras(source)
                self.assertEqual(processes.call_count, calls)
                self.assertEqual(fingerprints.call_count, 2)
                signature.assert_called_once()
                uploader._finish.assert_called_once_with(uploader._post.return_value, track_id)
                encode = lambda value: base64.b64encode(plistlib.dumps(value)).decode()
                record = {'track_id': track_id, 'requests': [
                    {'state': 'received', 'response': encode({})},
                    {'state': 'received', 'route': 'updateLibrary', 'response': encode({'status': 0}),
                     'request': encode({'cuid': 'test', 'troveid': 'test', 'persistent-library-id': 'test'})}]}
                with patch('prototype.uploader.load_session', return_value=record):
                    uploader.resume_pending(source)
                record.update(cloud_id=42, status=encode({}))
                record['requests'].append({'state': 'received', 'route': 'downloadRequests', 'response': encode({'status': 0})})
                with patch('prototype.uploader.load_session', return_value=record):
                    uploader.resume_work(source)
                self.assertEqual(processes.call_count, calls)
                self.assertEqual(uploader.signature, b'signature')
                self.assertEqual(uploader._fingerprints, {'partial': b'partial', 'full-lowres': b'full-lowres'})
                with patch.object(uploader, '_asset_data', side_effect=AssertionError('不应重新读取资产')):
                    for clean in (False, True):
                        self.assertEqual(uploader._asset_metadata('audio', clean)['hash-values']['sha256'], hashlib.sha256(b'AAC!' if not clean else source.read_bytes()).hexdigest())

    def test_单并发准备不计算指纹且源文件变化不复用旧结果(self):
        with tempfile.TemporaryDirectory() as temporary:
            uploader, source, run = self.make_uploader(Path(temporary))
            with patch('prototype.uploader.subprocess.run', side_effect=run) as processes, \
                    patch('prototype.uploader.generate_fingerprint') as fingerprints, \
                    patch('prototype.uploader.generate_signature') as signature:
                uploader.prepare(source)
                fingerprints.assert_not_called()
                signature.assert_not_called()
                original_id = uploader._prepared_media[2]['persistent-id']
                original_calls = processes.call_count
                uploader.signature = b'old-signature'
                uploader._fingerprints = {'partial': b'old-fingerprint'}
                source.write_bytes(struct.pack('>I4s', 12, b'mdat') + b'NEW!')
                uploader.prepare(source)
                self.assertGreater(processes.call_count, original_calls)
                self.assertNotEqual(uploader._prepared_media[2]['persistent-id'], original_id)
                self.assertIsNone(uploader.signature)
                self.assertEqual(uploader._fingerprints, {})
                self.assertEqual(uploader._asset_metadata('audio')['hash-values']['sha256'], hashlib.sha256(b'NEW!').hexdigest())


@unittest.skipIf(os.name == 'nt', '使用 Linux 服务端进程和会话文件锁')
class PreparationProcessTests(unittest.TestCase):
    def test_两首同时准备但协议会话始终互斥(self):
        script = '''
import json, sys, time, uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import worker, runtime, prototype.uploader
directory, index = Path(sys.argv[1]), sys.argv[2]
worker.PRIVATE = runtime.PRIVATE = directory
w = worker.Worker.__new__(worker.Worker)
w.managed = True
w.binding = {'account_scope': 'test'}
w.ffmpeg = Path('fake-ffmpeg')
w.server_verified_at = None
w.rejected_authorization_mtime = None
w.save = lambda path, value: path.write_text(json.dumps(value))
w.load = lambda path: json.loads(path.read_text())
w.save_state = lambda: None
w.readiness = lambda: dict(authorization_saved=True, client_exited=True, compatible=True, context_matches=True)
w.json_request = lambda *args: {'accepted': True}
w.download = lambda *args: directory / (index + '.m4a')
job = dict(job_id=str(uuid.uuid4()), sha256=index * 64, size=1, lease_token='test', action='upload', attempt=0, precompute_fingerprints=True)
job['content_url'] = '/api/apple-music/uploads/' + job['job_id'] + '/content'
def event(stage):
    with (directory / 'events').open('a') as stream:
        stream.write(index + ':' + stage + '\\n')
class FakeUploader:
    def __init__(self, *args):
        self.opener = SimpleNamespace(open=Mock())
    def prepare(self, source, **kwargs):
        event('prepare-start')
        (directory / (index + '.ready')).touch()
        deadline = time.monotonic() + 10
        while len(list(directory.glob('*.ready'))) < 2:
            if time.monotonic() > deadline:
                raise RuntimeError('本地准备未并行')
            time.sleep(0.01)
        event('prepare-end')
    def upload(self, source):
        event('session-start')
        time.sleep(0.1)
        event('session-end')
        w.save(directory / ('upload-' + job['sha256'] + '.dpapi'), dict(completed=True, complete_received=True))
        return {'extras_completed': True}
prototype.uploader.WindowsSongUploader = FakeUploader
w.execute(job)
assert w.load(directory / (job['job_id'] + '.dpapi'))['final_event']['state'] == 'cloud_completed'
'''
        with tempfile.TemporaryDirectory() as temporary:
            processes = [subprocess.Popen([sys.executable, '-c', script, temporary, index],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) for index in ('a', 'b')]
            try:
                for process in processes:
                    output, error = process.communicate(timeout=20)
                    self.assertEqual(process.returncode, 0, error.decode())
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()
            events = (Path(temporary) / 'events').read_text().splitlines()
            starts = [events.index(index + ':prepare-start') for index in ('a', 'b')]
            ends = [events.index(index + ':prepare-end') for index in ('a', 'b')]
            self.assertLess(max(starts), min(ends))
            sessions = [event.split(':')[1] for event in events if ':session-' in event]
            self.assertEqual(sessions, ['session-start', 'session-end', 'session-start', 'session-end'])


if __name__ == '__main__':
    unittest.main()
