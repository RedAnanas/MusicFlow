"""验证音频哈希范围与无效原子的处理。"""

import struct
import unittest

from prototype.audio_asset import m4a_audio_data


class AudioAssetTests(unittest.TestCase):
    def test_哈希数据不包含容器头和标签(self):
        data = struct.pack(">I4s", 12, b"ftyp") + b"M4A "
        data += struct.pack(">I4s", 12, b"mdat") + b"AAC!"
        data += struct.pack(">I4s", 12, b"moov") + b"tags"
        self.assertEqual(m4a_audio_data(data), b"AAC!")

    def test_扩展长度和末尾长度原子(self):
        self.assertEqual(m4a_audio_data(struct.pack(">I4sQ", 1, b"mdat", 20) + b"AAC!"), b"AAC!")
        self.assertEqual(m4a_audio_data(struct.pack(">I4s", 0, b"mdat") + b"AAC!"), b"AAC!")

    def test_拒绝截断越界和多个数据原子(self):
        atom = struct.pack(">I4s", 12, b"mdat") + b"AAC!"
        for data in (b"mdat", struct.pack(">I4s", 200, b"mdat"), atom + atom):
            with self.subTest(data_length=len(data)), self.assertRaises(ValueError):
                m4a_audio_data(data)
