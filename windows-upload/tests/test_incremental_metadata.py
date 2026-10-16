"""防止单曲上传意外复制或替换其他资料库内容。"""

import gzip
import plistlib
import unittest

from prototype.incremental_metadata import single_track_payload


class IncrementalMetadataTests(unittest.TestCase):
    def test_整库模板只提供必要标识且增量始终启用(self):
        library = {"persistent-library-id": "TEST-LIBRARY", "itre": 1,
                   "tracks": [{"item-name": "无关歌曲"}], "playlists": [{"name": "无关歌单"}]}
        common = {"cuid": "test", "troveid": "test", "incremental": False,
                  "cloud-incremental-update": False, "num-tracks": 100, "protocol-version": 1}
        track = {"persistent-id": "TEST-TRACK", "item-name": "上传测试"}
        result = single_track_payload(library, common, track)
        body = plistlib.loads(gzip.decompress(result["preformatted-data"]))
        self.assertEqual(body["tracks"], [track])
        self.assertTrue(body["incremental"])
        self.assertTrue(body["cloud-incremental-update"])
        self.assertNotIn("playlists", body)
        self.assertNotIn("num-tracks", body)
        self.assertEqual(library["tracks"][0]["item-name"], "无关歌曲")

    def test_新增单曲不能指向既有云歌曲(self):
        with self.assertRaises(ValueError):
            single_track_payload({}, {"cuid": "test", "troveid": "test"},
                                 {"persistent-id": "test", "cloud-id": "existing"})
