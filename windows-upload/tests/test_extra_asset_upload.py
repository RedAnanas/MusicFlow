"""验证资产请求、云歌曲隔离、恢复行为及完成票据。"""

import base64
from copy import deepcopy
import gzip
import hashlib
import plistlib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from prototype.extra_asset_upload import asset_metadata, upload_extras
from prototype.uploader import SongUploadError, WindowsSongUploader


class ExtraAssetUploadTests(unittest.TestCase):
    def uploader(self, replies):
        return SimpleNamespace(state={"cloud_id": 123, "requests": []}, common={"cuid": "test"},
            job="test.dpapi", account={"upload_configuration": {"cloud-assets-update": "initial"},
                                      "headers": {"User-Agent": "test"}},
            progress=Mock(), _post=Mock(side_effect=replies))

    def replies(self):
        return [{"download-requests-url": "download", "upload-responses-url": "upload"},
            {"payload": [{"cloud-id": 123, "actions": [{"action": "upload-track",
             "assets": {"artwork": {"upload-info": {}}, "lyrics": {"upload-info": {}}},
             "response-data": {"test": True}}]}]},
            {"payload": [{"cloud-id": 123, "actions": [{"token-artwork": "cover-token", "token-lyrics": "lyrics-token"}]}]},
            {"all-work-completed": True}]

    def test_歌词按原文本UTF8计算大小与摘要(self):
        data = "[00:01.00]测试歌词\n".encode("utf-8")
        metadata = asset_metadata(data)
        self.assertEqual(metadata, {"file-size": len(data), "hash-values": {
            "md5": hashlib.md5(data).hexdigest(), "sha256": hashlib.sha256(data).hexdigest()}})

    @patch("prototype.extra_asset_upload.time.sleep")
    @patch("prototype.extra_asset_upload.save_session")
    @patch("prototype.extra_asset_upload.upload_asset", return_value=[200])
    def test_上传两种资产并等待云端完成且重复调用不发送请求(self, transfer, save, sleep):
        uploader = self.uploader(self.replies())
        assets = {"artwork": b"jpeg", "lyrics": b"lyrics"}
        result = upload_extras(uploader, assets)
        self.assertTrue(result["extras_completed"])
        self.assertEqual(transfer.call_count, 2)
        initial = uploader._post.call_args_list[0].args[1]
        self.assertEqual(initial["payload"]["cloud-ids"], [123])
        self.assertEqual(initial["payload"]["lyrics"], asset_metadata(b"lyrics"))
        response = uploader._post.call_args_list[2].args[1]["payload"][0]["actions"][0]
        self.assertEqual(response["response-data"], {"test": True})
        self.assertEqual(response["assets"]["lyrics"], {"response-code": 200})
        upload_extras(uploader, assets)
        self.assertEqual(uploader._post.call_count, 4)

    @patch("prototype.extra_asset_upload.save_session")
    @patch("prototype.extra_asset_upload.upload_asset")
    def test_其他云歌曲任务禁止执行(self, transfer, save):
        replies = self.replies()
        replies[1]["payload"][0]["cloud-id"] = 999
        uploader = self.uploader(replies)
        with self.assertRaises(SongUploadError):
            upload_extras(uploader, {"artwork": b"jpeg", "lyrics": b"lyrics"})
        transfer.assert_not_called()

    @patch("prototype.extra_asset_upload.save_session")
    def test_只有会话结束而无资产票据不能报告成功(self, save):
        uploader = self.uploader([{"all-work-completed": True}])
        with self.assertRaises(SongUploadError):
            upload_extras(uploader, {"lyrics": b"lyrics"})
        self.assertFalse(uploader.state.get("completed", False))

    def test_未知请求结果禁止自动重发(self):
        uploader = self.uploader([])
        uploader.state["requests"] = [{"state": "prepared"}]
        with self.assertRaises(SongUploadError):
            upload_extras(uploader, {"lyrics": b"lyrics"})
        uploader._post.assert_not_called()

    @patch("prototype.extra_asset_upload.time.sleep")
    @patch("prototype.extra_asset_upload.save_session")
    @patch("prototype.extra_asset_upload.upload_asset", return_value=[200])
    def test_回报前中断沿用任务不重复发送成功资产(self, transfer, save, sleep):
        replies = self.replies()
        uploader = self.uploader([*replies[:2], OSError("测试中断")])
        assets = {"artwork": b"jpeg", "lyrics": b"lyrics"}
        with self.assertRaises(OSError):
            upload_extras(uploader, assets)
        self.assertEqual(transfer.call_count, 2)
        uploader._post = Mock(side_effect=replies[2:])
        self.assertTrue(upload_extras(uploader, assets)["extras_completed"])
        self.assertEqual(transfer.call_count, 2)
        self.assertEqual(uploader._post.call_args_list[0].args[0], "upload")

    @patch("prototype.extra_asset_upload.save_session")
    def test_会话错误不得被完成标记覆盖(self, save):
        uploader = self.uploader([{"all-work-completed": True, "error": 100}])
        with self.assertRaises(SongUploadError):
            upload_extras(uploader, {"lyrics": b"lyrics"})
        self.assertFalse(uploader.state.get("completed", False))

    @patch("prototype.extra_asset_upload.time.sleep")
    @patch("prototype.extra_asset_upload.upload_asset", return_value=[200])
    def test_响应已保存但阶段标记未保存时恢复各阶段不重发(self, transfer, sleep):
        endpoint = "https://genius-3.itunes.apple.com/SGCourier/updateAssets/"
        download = "https://genius-download-2.itunes.apple.com/SGCourier/downloadRequests/?test=1"
        upload = "https://genius-download-2.itunes.apple.com/SGCourier/uploadResponses/?test=1"
        replies = [{"status": 0, **reply} for reply in self.replies()]
        replies[0].update({"download-requests-url": download, "upload-responses-url": upload})
        assets = {"artwork": b"jpeg", "lyrics": b"lyrics"}
        for phase in ("initial", "work", "result", "availability"):
            with self.subTest(phase=phase):
                transfer.reset_mock()
                uploader = WindowsSongUploader.__new__(WindowsSongUploader)
                uploader.state = {"cloud_id": 123, "requests": []}
                uploader.common = {"cuid": "test"}
                uploader.job = "unused-test.dpapi"
                uploader.progress = Mock()
                uploader.account = {"headers": {"User-Agent": "test"},
                                    "upload_configuration": {"cloud-assets-update": endpoint}}
                uploader.signer = Mock()
                uploader.signer.sign.return_value = b"test-signature"
                uploader.opener = Mock()
                responses = []
                for reply in replies:
                    response = Mock(status=200, headers={"Content-Encoding": "gzip"})
                    response.read.return_value = gzip.compress(plistlib.dumps(reply))
                    response.__enter__ = Mock(return_value=response)
                    response.__exit__ = Mock(return_value=False)
                    responses.append(response)
                uploader.opener.open.side_effect = responses
                persisted = {}

                def persist_request(path, state):
                    persisted.clear()
                    persisted.update(deepcopy(state))

                def persist_stage(path, state):
                    if phase in state:
                        raise OSError("模拟阶段标记保存前中断")

                with patch("prototype.uploader.save_session", side_effect=persist_request), \
                        patch("prototype.extra_asset_upload.save_session", side_effect=persist_stage):
                    with self.assertRaises(OSError):
                        upload_extras(uploader, assets)
                self.assertNotIn(phase, persisted)
                received = len(persisted["requests"])
                uploader.state = deepcopy(persisted)
                with patch("prototype.uploader.save_session"), patch("prototype.extra_asset_upload.save_session"):
                    self.assertTrue(upload_extras(uploader, assets)["extras_completed"])
                self.assertEqual(uploader.opener.open.call_count, 4)
                self.assertEqual(transfer.call_count, 2)
                self.assertEqual(len(uploader.state["requests"]), 4)
                self.assertEqual(received, ("initial", "work", "result", "availability").index(phase) + 1)

    @patch("prototype.extra_asset_upload.save_session")
    def test_已保存的失败响应禁止恢复重发(self, save):
        uploader = self.uploader([])
        uploader.state["requests"] = [{"state": "received", "route": None,
            "response": base64.b64encode(plistlib.dumps({"status": 500})).decode("ascii")}]
        with self.assertRaises(SongUploadError):
            upload_extras(uploader, {"lyrics": b"lyrics"})
        uploader._post.assert_not_called()
