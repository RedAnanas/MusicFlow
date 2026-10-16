"""工作进程只使用假上传器验证恢复，不发送 Apple 请求或读取真实授权。"""

from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import uuid

from worker import Worker, WorkerError, recovery_action, validate_url


class WorkerTests(unittest.TestCase):
    def test_服务端请求更新授权后不再领取新任务(self):
        """授权导入只暂停后续领取，不抢占当前上传。"""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / '.pause-for-authorization').touch()
            worker = Worker.__new__(Worker)
            worker.report_saved_results = Mock()
            worker.json_request = Mock()
            with patch('worker.PRIVATE', directory), patch('worker.os', SimpleNamespace(name='posix')):
                worker.run()
            worker.json_request.assert_not_called()

    def test_结果不明和资产请求中断不自动重发(self):
        self.assertIsNone(recovery_action({"requests": [{"state": "prepared"}]}))
        self.assertIsNone(recovery_action({"completed": True, "complete_received": True}, True))
        self.assertIsNone(recovery_action({"requests": []}))
        self.assertIsNone(recovery_action(None, True))

    def test_根据持久记录选择最小恢复动作(self):
        self.assertEqual(recovery_action(None), "upload")
        self.assertEqual(recovery_action({"completed": True, "complete_received": True}), "upload_media_extras")
        pending = {"requests": [{"state": "received"}, {"state": "received", "route": "updateLibrary"}]}
        self.assertEqual(recovery_action(pending), "resume_pending")
        self.assertEqual(recovery_action({"cloud_id": "private-placeholder", "status": "opaque", "requests": [{"state": "received", "route": "downloadRequests"}]}), "resume_work")

    def test_后端地址拒绝凭据参数和其他协议(self):
        self.assertEqual(validate_url("http://127.0.0.1:8082/"), "http://127.0.0.1:8082")
        for url in ("file:///private", "https://user:secret@example.com", "https://example.com?token=test", "https://example.com/other"):
            with self.subTest(url=url), self.assertRaises(WorkerError):
                validate_url(url)

    def make_worker(self, directory):
        worker = Worker.__new__(Worker)
        worker.binding = {"account_scope": "test-scope", "worker_id": "test-worker"}
        worker.ffmpeg = Path("ffmpeg.exe")
        worker.server_verified_at = None
        worker.rejected_authorization_mtime = None
        records = {}

        def save(path, value):
            records[str(path)] = deepcopy(value)
            Path(path).write_bytes(b"fake-encrypted-test-record")

        worker.save = save
        worker.load = lambda path: deepcopy(records[str(path)])
        worker.json_request = Mock(return_value={"accepted": True})
        worker.download = Mock(return_value=directory / "song.m4a")
        worker.readiness = Mock(return_value=dict(authorization_saved=True, client_exited=True, compatible=True, context_matches=True))
        job = {"job_id": str(uuid.uuid4()), "sha256": "a" * 64, "size": 1, "lease_token": "first-test-lease",
               "action": "upload", "attempt": 0}
        job["content_url"] = f"/api/apple-music/uploads/{job['job_id']}/content"
        return worker, records, job

    def test_已完成但未回报时只重报结果(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker, records, job = self.make_worker(directory)
            worker.save(directory / (job["job_id"] + ".dpapi"), {
                "sha256": job["sha256"], "account_scope": "test-scope",
                "final_event": {"state": "cloud_completed", "action": "report_completed",
                                "evidence": {key: True for key in ("complete_received", "all_work_completed", "extras_completed")}}})
            with patch("worker.PRIVATE", directory), patch("prototype.uploader.WindowsSongUploader") as uploader:
                worker.execute(job)
            uploader.assert_not_called()
            worker.download.assert_not_called()
            self.assertEqual(worker.json_request.call_args.args[1]["state"], "cloud_completed")

    def test_终态响应已到达但本地未标记时重用原事件序号(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker, records, job = self.make_worker(directory)
            path = directory / (job["job_id"] + ".dpapi")
            worker.save(path, {"account_scope": "test-scope", "final_event": {"state": "cloud_completed"},
                               "lease_token": job["lease_token"], "sequence": 3, "final_sequence": 3})
            with patch("worker.PRIVATE", directory):
                worker.report_saved_results()
            self.assertEqual(worker.json_request.call_args.args[1]["sequence"], 3)
            self.assertTrue(worker.load(path)["reported"])

    def test_明确失败后的新轮次允许恢复而不永远重报旧失败(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker, records, job = self.make_worker(directory)
            worker.save(directory / (job["job_id"] + ".dpapi"), {
                "sha256": job["sha256"], "account_scope": "test-scope", "attempt": 0,
                "final_event": {"state": "failed", "action": "upload"}})
            job["attempt"] = 1

            def upload(source):
                worker.save(directory / f"upload-{job['sha256']}.dpapi", {"completed": True, "complete_received": True})
                return {"extras_completed": True}

            with patch("worker.PRIVATE", directory), patch("prototype.uploader.WindowsSongUploader") as uploader:
                uploader.return_value.upload.side_effect = upload
                worker.execute(job)
            uploader.return_value.upload.assert_called_once()
            self.assertEqual(worker.json_request.call_args.args[1]["state"], "cloud_completed")

    def test_未知请求结果只报告人工核对(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker, records, job = self.make_worker(directory)
            worker.save(directory / f"upload-{job['sha256']}.dpapi", {"requests": [{"state": "prepared"}]})
            with patch("worker.PRIVATE", directory), patch("prototype.uploader.WindowsSongUploader") as uploader:
                worker.execute(job)
            uploader.return_value.upload.assert_not_called()
            self.assertEqual(worker.json_request.call_args.args[1]["state"], "requires_review")

    def test_请求记录丢失时不能把原任务当作新上传(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker, records, job = self.make_worker(directory)
            job["recovery_required"] = True
            with patch("worker.PRIVATE", directory), patch("prototype.uploader.WindowsSongUploader") as uploader:
                worker.execute(job)
            uploader.return_value.upload.assert_not_called()
            self.assertEqual(worker.json_request.call_args.args[1]["state"], "requires_review")

    def test_额外资产控制请求结果不明时不再次补传(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker, records, job = self.make_worker(directory)
            worker.save(directory / f"upload-{job['sha256']}.dpapi", {"completed": True, "complete_received": True})
            worker.save(directory / f"asset-upload-{job['sha256']}.dpapi", {"requests": [{"state": "prepared"}]})
            with patch("worker.PRIVATE", directory), patch("prototype.uploader.WindowsSongUploader") as uploader:
                worker.execute(job)
            uploader.return_value.upload_media_extras.assert_not_called()
            self.assertEqual(worker.json_request.call_args.args[1]["state"], "requires_review")

    def test_成品下载失败时不调用上传器(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker, records, job = self.make_worker(directory)
            worker.download.side_effect = WorkerError("成品完整性校验失败")
            with patch("worker.PRIVATE", directory), patch("prototype.uploader.WindowsSongUploader") as uploader:
                worker.execute(job)
            uploader.assert_not_called()
            self.assertEqual(worker.json_request.call_args.args[1]["error_code"], "content_changed")

    def test_音频已完成时只补传资产(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker, records, job = self.make_worker(directory)
            worker.save(directory / f"upload-{job['sha256']}.dpapi", {"completed": True, "complete_received": True})
            with patch("worker.PRIVATE", directory), patch("prototype.uploader.WindowsSongUploader") as uploader:
                uploader.return_value.upload_media_extras.return_value = {"extras_completed": True}
                worker.execute(job)
            uploader.return_value.upload.assert_not_called()
            uploader.return_value.upload_media_extras.assert_called_once()

    def test_耗时签名期间持续发送有序心跳(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker, records, job = self.make_worker(directory)
            worker.HEARTBEAT_SECONDS = 0.01

            def upload(source):
                time.sleep(0.06)
                worker.save(directory / f"upload-{job['sha256']}.dpapi", {"completed": True, "complete_received": True})
                return {"extras_completed": True}

            with patch("worker.PRIVATE", directory), patch("prototype.uploader.WindowsSongUploader") as uploader:
                uploader.return_value.upload.side_effect = upload
                worker.execute(job)
            events = [call.args[1] for call in worker.json_request.call_args_list]
            self.assertGreater(len(events), 4)
            self.assertEqual([item["sequence"] for item in events], list(range(1, len(events) + 1)))


if __name__ == "__main__":
    unittest.main()
