"""离线验证签名缓存命中、隔离和损坏恢复，不发起上传。"""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from prototype.uploader import WindowsSongUploader, SongUploadError


class SignatureCacheTests(unittest.TestCase):
    def uploader(self, root, audio=b'audio'):
        value = WindowsSongUploader.__new__(WindowsSongUploader)
        value.private = root
        value.directory = root / 'media'
        value.directory.mkdir(exist_ok=True)
        (value.directory / 'signature.pcm').write_bytes(audio)
        value.audio = audio
        value.signature = None
        value.source = Path('song.m4a')
        value.ffmpeg = Path('ffmpeg')
        value.progress = Mock()
        return value

    @patch('prototype.uploader.subprocess.run', return_value=Mock(returncode=0))
    @patch('prototype.uploader.generate_signature', return_value=b'signature')
    def test_同解码音频跨任务命中缓存无需再次仿真(self, generate, run):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(self.uploader(root)._signature(), b'signature')
            value = self.uploader(root)
            self.assertEqual(value._signature(), b'signature')
            generate.assert_called_once()
            self.assertEqual(run.call_count, 2)
            self.assertEqual(value.progress.call_args.args, ('signature', 100))

    @patch('prototype.uploader.subprocess.run', return_value=Mock(returncode=0))
    @patch('prototype.uploader.generate_signature', return_value=b'signature')
    def test_音频或算法版本变化不能复用缓存(self, generate, run):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.uploader(root)._signature()
            self.uploader(root, b'other-audio')._signature()
            with patch('prototype.uploader.windows_sap.EXPECTED', 'other-version'):
                self.uploader(root)._signature()
            self.assertEqual(generate.call_count, 3)

    @patch('prototype.uploader.subprocess.run', return_value=Mock(returncode=0))
    @patch('prototype.uploader.generate_signature', return_value=b'signature')
    def test_相同载荷解码裁剪不同不能误用签名(self, generate, run):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.uploader(root)._signature()
            value = self.uploader(root)
            (value.directory / 'signature.pcm').write_bytes(b'trimmed-pcm')
            value._signature()
            self.assertEqual(generate.call_count, 2)

    @patch('prototype.uploader.subprocess.run', return_value=Mock(returncode=0))
    @patch('prototype.uploader.generate_signature', return_value=b'signature')
    def test_缓存损坏重新生成且失败不写入新缓存(self, generate, run):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.uploader(root)._signature()
            target = next((root / 'signature-cache').glob('*.bin'))
            target.write_bytes(b'broken-signature-cache' * 3)
            self.assertEqual(self.uploader(root)._signature(), b'signature')
            self.assertEqual(generate.call_count, 2)
            generate.side_effect = RuntimeError('仿真失败')
            with self.assertRaises(RuntimeError):
                self.uploader(root, b'new-audio')._signature()
            self.assertEqual(len(list((root / 'signature-cache').glob('*.bin'))), 1)

    @unittest.skipIf(os.name == 'nt', '符号链接隔离在 Linux 验证')
    def test_拒绝缓存目录符号链接(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'other').mkdir()
            (root / 'signature-cache').symlink_to(root / 'other', target_is_directory=True)
            with self.assertRaises(SongUploadError):
                self.uploader(root)._signature()
