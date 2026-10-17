"""验证真实描述符语义、范围边界与网络失败脱敏。"""

import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from urllib.request import Request
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from prototype.upload_asset import UploadError, build_requests, upload_asset


def descriptor(offset=0, length=4):
    return {"operations": [{
        "method": "PUT",
        "endpoint": "https://store-033.blobstore.apple.com/asset?ticket=private-value",
        "requiredHeaders": [
            {"key": "Date", "clientGenerated": True},
            {"key": "Content-Length", "value": str(length)},
            {"key": "Content-MD5", "value": "server-provided-digest"},
        ],
        "optionalHeaders": [{"key": "User-Agent", "clientGenerated": True}],
        "content": {"type": "byterange", "offset": offset, "length": length},
    }]}


class UploadAssetTests(unittest.TestCase):
    def test_真实本机连接验证流式请求不改变传输字节(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_PUT(self):
                received.append(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        data = b'test-audio' * 20000
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(f'http://127.0.0.1:{server.server_port}/', data=data, method='PUT')
            with patch('prototype.upload_asset.build_requests', return_value=[request]):
                self.assertEqual(upload_asset({}, data, 'test', lambda *args: None), [200])
            self.assertEqual(received, [data])
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_流式进度保持原始请求字节和长度并等待服务端确认(self):
        data = b'a' * 150000
        updates = []

        def open_request(request, timeout):
            self.assertEqual(request.get_header('Content-length'), str(len(data)))
            self.assertEqual(b''.join(request.data), data)
            self.assertTrue(all(done < total for done, total in updates))
            response = MagicMock()
            response.__enter__.return_value.status = 200
            return response

        with patch('prototype.upload_asset.build_opener') as opener:
            opener.return_value.open.side_effect = open_request
            self.assertEqual(upload_asset(descriptor(0, len(data)), data, 'test', lambda done, total: updates.append((done, total))), [200])
        self.assertGreater(len(updates), 2)
        self.assertEqual(updates[-1], (len(data), len(data)))

    def test_服务端拒绝不显示传输完成(self):
        updates = []

        def reject(request, timeout):
            list(request.data)
            raise HTTPError('https://test', 503, 'test', {}, None)

        with patch('prototype.upload_asset.build_opener') as opener:
            opener.return_value.open.side_effect = reject
            with self.assertRaises(UploadError):
                upload_asset(descriptor(), b'test', 'test', lambda done, total: updates.append((done, total)))
        self.assertTrue(all(done < total for done, total in updates))

    def test_歌词封面任务接受十进制字符串范围并拒绝异常格式(self):
        self.assertEqual(build_requests(descriptor("2", "4"), b"001234", "test")[0].data, b"1234")
        for offset in ("-1", "1.0", " 1", "１", "1e0"):
            with self.subTest(offset=offset), self.assertRaises(UploadError):
                build_requests(descriptor(offset, "4"), b"001234", "test")

    def test_按偏移取数据并生成允许的请求头(self):
        request = build_requests(descriptor(2, 4), b"00123499", "MusicFlow-Test")[0]
        self.assertEqual(request.data, b"1234")
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.get_header("User-agent"), "MusicFlow-Test")
        self.assertTrue(request.get_header("Date").endswith("GMT"))
        self.assertEqual(request.get_header("Content-md5"), "server-provided-digest")

    def test_分段不能超出数据范围(self):
        for offset, length in ((-1, 2), (2, 4), (0, 0), (True, 1)):
            with self.subTest(offset=offset, length=length), self.assertRaises(UploadError):
                build_requests(descriptor(offset, length), b"1234", "test")

    def test_多个操作保持各自偏移和顺序(self):
        value = descriptor(0, 2)
        value["operations"] += descriptor(2, 2)["operations"]
        self.assertEqual([r.data for r in build_requests(value, b"abcd", "test")], [b"ab", b"cd"])

    def test_内嵌二进制内容不替换为原始音频(self):
        value = descriptor(0, 3)
        value["operations"][0]["content"] = {"type": "verbatim", "content": b"abc"}
        self.assertEqual(build_requests(value, b"other", "test")[0].data, b"abc")

    def test_拒绝外部地址和请求头注入(self):
        for url in ("https://example.com/", "https://blobstore.apple.com.evil.test/", "http://store-033.blobstore.apple.com/"):
            value = descriptor()
            value["operations"][0]["endpoint"] = url
            with self.assertRaises(UploadError):
                build_requests(value, b"1234", "test")
        with self.assertRaises(UploadError):
            build_requests(descriptor(), b"1234", "test\r\nSecret: value")

    def test_失败消息不包含预签名地址(self):
        error = HTTPError("https://store-033.blobstore.apple.com/?ticket=private-value", 403, "private-value", {}, None)
        with patch("prototype.upload_asset.build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaisesRegex(UploadError, "HTTP 403") as caught:
                upload_asset(descriptor(), b"1234", "test")
        self.assertNotIn("private-value", str(caught.exception))

    def test_传输成功只返回资产状态(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        with patch("prototype.upload_asset.build_opener") as opener:
            opener.return_value.open.return_value = response
            self.assertEqual(upload_asset(descriptor(), b"1234", "test"), [200])


if __name__ == "__main__":
    unittest.main()
