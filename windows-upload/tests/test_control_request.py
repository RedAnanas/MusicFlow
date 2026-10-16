"""验证请求字节与签名绑定，以及未经验证的地址和传输字段隔离。"""

import gzip
import plistlib
import unittest
from unittest.mock import Mock

from prototype.control_request import ControlRequestError, build_control_request


ENDPOINT = "https://genius-upload-2.itunes.apple.com/WebObjects/SGCourier.woa/wa/uploadResponses"


class ControlRequestTests(unittest.TestCase):
    def test_资产初始化只允许确认的专用接口(self):
        signer = Mock()
        signer.sign.return_value = b"signature"
        endpoint = "https://genius-3.itunes.apple.com/SGCourier/updateAssets/"
        build_control_request(endpoint, {}, {}, signer)
        for invalid in (endpoint + "?test=1", endpoint.replace("genius-3", "genius-upload-2")):
            with self.assertRaises(ControlRequestError):
                build_control_request(invalid, {}, {}, signer)

    def test_签名绑定压缩后的实际请求字节(self):
        payload = {"test": "重复测试数据" * 100}
        signer = Mock()
        signer.sign.return_value = b"test-signature"
        request = build_control_request(ENDPOINT, payload, {"X-Token": "private-value"}, signer)
        signer.sign.assert_called_once_with(request.data)
        self.assertEqual(request.get_header("Content-encoding"), "gzip")
        self.assertEqual(plistlib.loads(gzip.decompress(request.data)), payload)
        self.assertEqual(request.get_header("Content-length"), str(len(request.data)))
        self.assertEqual(request.get_header("X-apple-actionsignature"), "dGVzdC1zaWduYXR1cmU=")

    def test_属性列表保留二进制布尔和数值类型(self):
        payload = {"data": b"\x00\xff", "flag": True, "count": 2}
        signer = Mock()
        signer.sign.return_value = b"signature"
        request = build_control_request(ENDPOINT, payload, {}, signer)
        raw = gzip.decompress(request.data) if request.get_header("Content-encoding") else request.data
        self.assertNotIn(b"<!DOCTYPE", raw)
        self.assertEqual(plistlib.loads(raw), payload)

    def test_拒绝未验证地址且不调用签名器(self):
        signer = Mock()
        for endpoint in ("https://example.com/", ENDPOINT.replace("https:", "http:"), ENDPOINT + "?secret=value"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ControlRequestError):
                build_control_request(endpoint, {}, {}, signer)
        signer.sign.assert_not_called()

    def test_拒绝旧签名及长度覆盖并脱敏错误(self):
        for key in ("X-Apple-ActionSignature", "Content-Length", "Host"):
            with self.subTest(key=key), self.assertRaises(ControlRequestError) as error:
                build_control_request(ENDPOINT, {}, {key: "private-value"}, Mock())
            self.assertNotIn("private-value", str(error.exception))

    def test_工作请求保留服务端查询参数且限定路由(self):
        endpoint = "https://genius-download-2.itunes.apple.com/SGCourier/downloadRequests/?session-id=test"
        signer = Mock()
        signer.sign.return_value = b"signature"
        request = build_control_request(endpoint, {"session-id": 1}, {}, signer, server_route="downloadRequests")
        self.assertEqual(request.full_url, endpoint)
        signer.sign.assert_called_once_with(request.data)
        for invalid in (endpoint.replace("downloadRequests", "uploadResponses"),
                        endpoint.replace("genius-download-2", "genius-upload-2")):
            with self.subTest(endpoint=invalid), self.assertRaises(ControlRequestError):
                build_control_request(invalid, {}, {}, signer, server_route="downloadRequests")

    def test_预编码数据直接签名且不二次包装(self):
        encoded = gzip.compress(plistlib.dumps({"tracks": []}), mtime=0)
        signer = Mock()
        signer.sign.return_value = b"signature"
        request = build_control_request(ENDPOINT, {"preformatted-data": encoded}, {}, signer)
        self.assertEqual(request.data, encoded)
        self.assertEqual(request.get_header("Content-encoding"), "gzip")
        signer.sign.assert_called_once_with(encoded)
        with self.assertRaises(ControlRequestError):
            build_control_request(ENDPOINT, {"preformatted-data": b"plain-data"}, {}, signer)

    def test_仅补充字段路由允许不签名(self):
        endpoint = "https://genius-download-2.itunes.apple.com/getLibraryUpdateResponse/?update-id=test"
        request = build_control_request(endpoint, {}, {}, None, server_route="getLibraryUpdateResponse")
        self.assertIsNone(request.get_header("X-apple-actionsignature"))
        with self.assertRaises(ControlRequestError):
            build_control_request(ENDPOINT, {}, {}, None)


if __name__ == "__main__":
    unittest.main()
