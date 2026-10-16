"""验证工作任务处理和歌曲完成状态，避免误报或泄漏工作票据。"""

import base64
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from prototype.uploader import SongUploadError, WindowsSongUploader


class UploaderTests(unittest.TestCase):
    def setUp(self):
        self.uploader = WindowsSongUploader.__new__(WindowsSongUploader)
        self.uploader.progress = lambda *args: None
        self.uploader.audio = b"test AAC bytes"
        self.uploader.state = {"complete_received": False}

    def test_哈希响应保留服务端回显且不修改输入(self):
        action = {"action": "hash-track", "assets": {"audio": {"hash-type": "sha256"}},
                  "response-data": {"token": "private-placeholder"}}
        response = self.uploader._action(action)
        self.assertEqual(response["assets"]["audio"]["hash-value"], hashlib.sha256(self.uploader.audio).hexdigest())
        self.assertEqual(response["assets"]["audio"]["status"], 0)
        self.assertEqual(response["response-data"], action["response-data"])
        self.assertNotIn("hash-value", action["assets"]["audio"])

    def test_单曲完成不需要回报伪造资产成功(self):
        self.assertIsNone(self.uploader._action({"action": "complete", "token-audio": "private-placeholder"}))
        self.assertTrue(self.uploader.state["complete_received"])
        self.assertNotIn("audio_uploaded", self.uploader.state)

    def test_同一哈希任务按类型计算音频封面歌词摘要(self):
        with tempfile.TemporaryDirectory() as temporary:
            cover = Path(temporary) / "cover.jpg"
            cover.write_bytes(b"jpeg")
            self.uploader.extras = {"cover": {"path": cover}, "lyrics": "[00:01]测试"}
            action = {"action": "hash-track", "assets": {k: {"hash-type": "sha256"}
                      for k in ("audio", "artwork", "lyrics")}}
            reply = self.uploader._action(action)
            self.assertEqual(reply["assets"]["artwork"]["hash-value"], hashlib.sha256(b"jpeg").hexdigest())
            self.assertEqual(reply["assets"]["lyrics"]["hash-value"], hashlib.sha256("[00:01]测试".encode()).hexdigest())
            self.assertNotIn("hash-value", action["assets"]["lyrics"])

    @patch("prototype.uploader.upload_asset", return_value=[200])
    def test_准备和上传任务使用各自资产原字节(self, transfer):
        with tempfile.TemporaryDirectory() as temporary:
            cover = Path(temporary) / "cover.jpg"
            cover.write_bytes(b"jpeg")
            self.uploader.clean = Path(temporary) / "clean.m4a"
            self.uploader.clean.write_bytes(b"clean audio")
            self.uploader.extras = {"cover": {"path": cover}, "lyrics": "测试"}
            self.uploader.account = {"headers": {"User-Agent": "test"}}
            expected = {"artwork": b"jpeg", "lyrics": "测试".encode(), "audio": b"clean audio"}
            prepare = {"action": "prepare-track", "assets": {k: {"hash-type": "md5"} for k in expected}}
            prepare["assets"]["audio"]["upload-type"] = "clean"
            response = self.uploader._action(prepare)
            for kind, data in expected.items():
                self.assertEqual(response["assets"][kind]["file-size"], len(data))
                self.assertEqual(response["assets"][kind]["hash-value"], hashlib.md5(data).hexdigest())
            upload = {"action": "upload-track", "assets": {k: {"upload-info": {}} for k in expected}}
            response = self.uploader._action(upload)
            self.assertEqual([c.args[1] for c in transfer.call_args_list], list(expected.values()))
            self.assertTrue(self.uploader.state["audio_uploaded"])
            self.assertEqual(response["assets"]["lyrics"]["response-code"], 200)
            self.assertIn("upload-info", upload["assets"]["lyrics"])

    @patch("prototype.uploader.WindowsSapSigner")
    @patch("prototype.uploader.load_session")
    @patch("prototype.uploader.extract_media_extras", return_value={"lyrics": "测试", "cover": None})
    @patch("prototype.uploader.subprocess.run", return_value=Mock(stdout=b"{}", returncode=0))
    def test_主上传已有资产完成票据时不再创建补传会话(self, probe, extract, load, signer):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "test.m4a"
            source.write_bytes(b"test")
            self.uploader.private = Path(temporary)
            self.uploader.ffprobe = Path("ffprobe.exe")
            self.uploader.ffmpeg = Path("ffmpeg.exe")
            self.uploader.context = {"common": {"cuid": "test-cuid", "troveid": "test-trove"},
                                     "persistent-library-id": "test-library"}
            metadata = {**self.uploader.context["common"], "persistent-library-id": "test-library"}
            load.return_value = {"completed": True, "cloud_id": 123, "complete_action":
                base64.b64encode(plistlib.dumps({"action": "complete", "token-lyrics": "test-token"})).decode(),
                "requests": [{"route": "updateLibrary", "request": base64.b64encode(plistlib.dumps(metadata)).decode()}]}
            result = self.uploader.upload_media_extras(source)
            self.assertTrue(result["extras_completed"])
            self.assertEqual(result["assets"], ["lyrics"])
            self.assertEqual(load.call_count, 1)
            signer.assert_not_called()

    def test_刷新授权后禁止恢复其他资料库的任务(self):
        self.uploader.context = {"common": {"cuid": "current-cuid", "troveid": "current-trove"},
                                 "persistent-library-id": "current-library"}
        metadata = {**self.uploader.context["common"], "persistent-library-id": "current-library"}
        state = {"requests": [{"route": "updateLibrary", "request": base64.b64encode(plistlib.dumps(metadata)).decode()}]}
        self.uploader._check_job_context(state)
        self.uploader.context["common"]["troveid"] = "another-trove"
        with self.assertRaises(SongUploadError):
            self.uploader._check_job_context(state)

    def test_错误完成票据不得置为完成(self):
        with self.assertRaises(SongUploadError):
            self.uploader._action({"action": "complete", "error": 4021})
        self.assertFalse(self.uploader.state["complete_received"])

    def test_未实现指纹任务明确失败且错误不带票据(self):
        with self.assertRaises(SongUploadError) as error:
            self.uploader._action({"action": "prepare-fingerprint", "fingerprint-type": "full-hires",
                                   "response-data": {"token": "private-placeholder"}})
        self.assertNotIn("private-placeholder", str(error.exception))

    def test_partial回报使用原始字节并保留回显(self):
        """指纹结果不能转为文本或改写服务器回显。"""
        self.uploader._fingerprint = Mock(return_value=b'fingerprint-bytes')
        action = {'action': 'get-fingerprint', 'fingerprint-type': 'partial', 'response-data': {'ticket': 'test'}}
        reply = self.uploader._action(action)
        self.assertEqual(reply['fingerprint-value'], b'fingerprint-bytes')
        self.assertEqual(reply['response-data'], action['response-data'])
        self.assertEqual(reply['status'], 0)
        self.assertNotIn('fingerprint-value', action)

    def test_full_lowres准备使用正确长度和摘要(self):
        """旧版指纹资产的准备结果对应实际二进制内容。"""
        self.uploader._fingerprint = Mock(return_value=b'lowres')
        reply = self.uploader._action({'action': 'prepare-fingerprint', 'fingerprint-type': 'full-lowres', 'hash-type': 'md5'})
        self.assertEqual(reply['file-size'], 6)
        self.assertEqual(reply['hash-value'], hashlib.md5(b'lowres').hexdigest())

    @patch('prototype.uploader.save_session')
    def test_首次空查询进入匹配态并遵守长等待(self, save):
        """首次无动作响应也要切状态，且不将三分钟等待截为一分钟。"""
        uploader = self.uploader
        status = {'session-id': 'test', 'upload-responses-url': 'responses', 'download-requests-url': 'work'}
        uploader.state.update(cloud_id=123, status=base64.b64encode(plistlib.dumps(status)).decode(), audio_uploaded=False)
        uploader.common, uploader.job, uploader.source = {}, Path('test.dpapi'), Path('test.m4a')
        uploader.upload_media_extras = Mock(return_value={'extras_completed': True})
        uploader._post = Mock(side_effect=[{'retry-in-ms': 180000, 'sequence-id': 2},
            {'all-work-completed': True, 'payload': [{'cloud-id': 123, 'actions': [{'action': 'complete'}]}]}])
        with patch('prototype.uploader.time.sleep') as sleep:
            result = uploader._finish(None, 'test', resume_reply={'retry-in-ms': 1000})
        self.assertTrue(result['completed'])
        calls = uploader._post.call_args_list
        self.assertEqual(calls[0].args[1]['match-state'], 12)
        self.assertEqual(calls[1].args[1]['match-state'], 13)
        self.assertEqual(calls[1].args[1]['sequence-id'], 2)
        self.assertNotIn('match-session', calls[1].args[1])
        self.assertIn(unittest.mock.call(180.0), sleep.call_args_list)

    def test_专辑标签使用已观测的协议字段(self):
        info = {"streams": [{"codec_type": "audio", "codec_name": "aac", "profile": "LC",
                             "duration": "60", "sample_rate": "44100", "bit_rate": "256000"}],
                "format": {"tags": {"TITLE": "测试歌曲", "ARTIST": "测试艺人", "ALBUM": "测试专辑",
                                    "album_artist": "专辑艺人", "composer": "测试作曲者",
                                    "date": "2026-10-15", "track": "4/12", "disc": "1/2"}}}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.m4a"
            data = struct.pack(">I4s", 12, b"mdat") + b"AAC!"
            source.write_bytes(data)
            (directory / "clean.m4a").write_bytes(data)
            self.uploader.ffprobe = Path("ffprobe.exe")
            self.uploader.ffmpeg = Path("ffmpeg.exe")
            with patch("prototype.uploader.subprocess.run", return_value=Mock(stdout=json.dumps(info).encode(), returncode=0)):
                track = self.uploader._media(source, directory)
            self.assertEqual(track.get("album"), "测试专辑")
            self.assertEqual(track.get("playlist-name"), "测试专辑")
            self.assertEqual(track.get("artist-name"), "测试艺人")
            self.assertEqual(track.get("artist"), "测试艺人")
            self.assertEqual(track.get("album-artist"), "专辑艺人")
            self.assertEqual(track.get("playlist-artist-name"), "专辑艺人")
            self.assertEqual(track.get("composer-name"), "测试作曲者")
            self.assertEqual(track.get("composer"), "测试作曲者")
            self.assertEqual(track.get("year"), 2026)
            self.assertEqual(track.get("track-number"), 4)
            self.assertEqual(track.get("track-count"), 12)
            self.assertEqual(track.get("disc-number"), 1)
            self.assertEqual(track.get("disc-count"), 2)
            self.assertNotIn("album-name", track)

    def test_元数据处理中遵守等待并继续同一会话(self):
        self.uploader.account = {"upload_configuration": {"cloud-library-update-check": "status-endpoint"}}
        self.uploader.common = {"protocol-version": 1}
        ready = {"additional-fields-url": "additional", "download-requests-url": "work"}
        self.uploader._post = Mock(side_effect=[{"retry-in-ms": 5000}, ready])
        with patch("prototype.uploader.time.sleep") as sleep:
            self.assertEqual(self.uploader._await_status({"update-id": "private-placeholder"}), ready)
        sleep.assert_called_once_with(5.0)
        self.assertEqual(self.uploader._post.call_count, 2)

    def test_缺少工作路由且没有等待指令时明确失败(self):
        self.uploader.account = {"upload_configuration": {"cloud-library-update-check": "status-endpoint"}}
        self.uploader.common = {}
        self.uploader._post = Mock(return_value={})
        with self.assertRaises(SongUploadError):
            self.uploader._await_status({"update-id": "private-placeholder"})

    @patch("prototype.uploader.save_session")
    def test_恢复已接收的工作响应不重新创建会话或提交元数据(self, save):
        uploader = self.uploader
        status = {"session-id": "test", "upload-responses-url": "responses", "download-requests-url": "work"}
        uploader.state.update(cloud_id=123, status=base64.b64encode(plistlib.dumps(status)).decode(), audio_uploaded=False)
        uploader.common = {}
        uploader.job = Path("test.dpapi")
        uploader.source = Path("test.m4a")
        uploader.upload_media_extras = Mock(return_value={"extras_completed": True})
        uploader._post = Mock(return_value={"all-work-completed": True, "payload": [
            {"cloud-id": 123, "actions": [{"action": "complete"}]}]})
        result = uploader._finish(None, "test", resume_reply={"payload": [
            {"cloud-id": 123, "actions": [{"action": "hash-track", "assets": {"audio": {"hash-type": "sha256"}}}]}]})
        self.assertTrue(result["completed"])
        self.assertEqual(uploader._post.call_count, 1)
        self.assertEqual(uploader._post.call_args.args[0], "responses")
        self.assertEqual(uploader._post.call_args.args[2], "uploadResponses")
