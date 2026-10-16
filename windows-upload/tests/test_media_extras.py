"""验证嵌入歌词和封面的读取不会修改源文件。"""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from prototype.media_extras import extract_media_extras


class MediaExtrasTests(unittest.TestCase):
    def test_无封面时保留完整歌词且不运行转码程序(self):
        lyrics = "[00:01.00]第一行\n[00:03.00]第二行"
        with patch("prototype.media_extras.subprocess.run") as run:
            result = extract_media_extras("source.m4a", {"format": {"tags": {"LYRICS": lyrics}}},
                                          "ffmpeg", "unused")
        self.assertEqual(result, {"lyrics": lyrics, "cover": None})
        run.assert_not_called()

    def test_封面按流索引原样复制且保留源文件(self):
        for codec, extension, content_type in (("mjpeg", "jpg", "image/jpeg"),
                                                ("png", "png", "image/png")):
            with self.subTest(codec=codec), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "source.m4a"
                source.write_bytes(b"original audio")
                output = Path(directory) / "output"
                image = b"embedded original image"

                def extract(command, **kwargs):
                    self.assertEqual(command[command.index("-map") + 1], "0:2")
                    self.assertEqual(command[command.index("-c:v") + 1], "copy")
                    Path(command[-1]).write_bytes(image)
                    return subprocess.CompletedProcess(command, 0)

                info = {"streams": [{"index": 0, "codec_name": "aac"},
                                     {"index": 2, "codec_name": codec,
                                      "disposition": {"attached_pic": 1}}]}
                with patch("prototype.media_extras.subprocess.run", side_effect=extract):
                    result = extract_media_extras(source, info, "ffmpeg", output)
                self.assertEqual(source.read_bytes(), b"original audio")
                self.assertEqual(result["cover"]["path"].suffix, "." + extension)
                self.assertEqual(result["cover"]["path"].read_bytes(), image)
                self.assertEqual(result["cover"]["size"], len(image))
                self.assertEqual(result["cover"]["content_type"], content_type)

    def test_提取失败不会泄漏工具错误或遗留半成品(self):
        with tempfile.TemporaryDirectory() as directory:
            info = {"streams": [{"index": 1, "codec_name": "png",
                                  "disposition": {"attached_pic": 1}}]}

            def fail(command, **kwargs):
                Path(command[-1]).write_bytes(b"partial")
                return subprocess.CompletedProcess(command, 1, stderr=b"private path")

            with patch("prototype.media_extras.subprocess.run", side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, "^嵌入封面提取失败$"):
                    extract_media_extras("source", info, "ffmpeg", directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
