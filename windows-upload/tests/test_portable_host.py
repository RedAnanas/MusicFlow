"""跨平台宿主接口的编码与缓冲区边界，不需要 Apple 二进制。"""
import ctypes
import unittest

from prototype.portable_host import HostAPI, decode_936


class PortableHostTests(unittest.TestCase):
    def setUp(self):
        self.host = HostAPI()

    def test_chinese_conversion_and_capacity(self):
        """中文按来宾 CP936 转换，容量不足时不写缓冲区。"""
        source = ctypes.create_string_buffer('中文'.encode('gbk'))
        output = ctypes.create_string_buffer(b'keep')
        convert = self.host.kernel32.MultiByteToWideChar
        self.assertEqual(convert(936, 1, source, 4, None, 0), 2)
        self.assertEqual(convert(936, 1, source, 4, output, 1), 0)
        self.assertEqual(output.raw, b'keep\0')
        self.assertEqual(convert(936, 1, source, 4, output, 2), 2)
        self.assertEqual(output.raw[:4].decode('utf-16-le'), '中文')

    def test_windows_single_byte_extensions(self):
        """Windows CP936 的两个单字节扩展保留原字符。"""
        self.assertEqual(decode_936(b'A\x80\xff'), 'A€\uf8f5')
        source = ctypes.create_string_buffer('€\uf8f5'.encode('utf-16-le'))
        output = ctypes.create_string_buffer(2)
        self.assertEqual(self.host.kernel32.WideCharToMultiByte(936, 0, source, 2, output, 2, None, None), 2)
        self.assertEqual(output.raw, b'\x80\xff')

    def test_case_mapping_is_not_casefold(self):
        """CRT 大小写映射保留普通大小写语义。"""
        source = ctypes.create_string_buffer('Ab中文'.encode('utf-16-le'))
        output = ctypes.create_string_buffer(8)
        self.assertEqual(self.host.kernel32.LCMapStringEx('zh-CN', 0x100, source, 4, output, 4, None, None, 0), 4)
        self.assertEqual(output.raw.decode('utf-16-le'), 'ab中文')

    def test_unknown_api_and_flags_stop(self):
        """未知接口或不支持的标志不能伪造成功。"""
        with self.assertRaises(AssertionError):
            self.host.kernel32.UnknownWindowsAPI()
        with self.assertRaises(AssertionError):
            self.host.kernel32.MultiByteToWideChar(936, 0xffff, None, 0, None, 0)
        with self.assertRaises(AttributeError):
            self.host.load_library('kernel32', winmode=0x800).UnknownWindowsAPI
