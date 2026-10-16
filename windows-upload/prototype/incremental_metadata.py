"""构造显式单曲增量元数据，不复制整库 tracks 或 playlists。"""

import gzip
import plistlib


COMMON_FIELDS = (
    "itunes-platform", "itunes-version", "protocol-version", "min-compatible-version",
    "cuid", "troveid", "itunes-match-protocol-version", "min-itunes-match-compatible-version",
    "machine-name", "library-name", "signature-generation-capable", "sims-are-optional",
    "auto-update", "cloud-manual-update",
)


def single_track_payload(library_template, common, track):
    """返回待签名的预编码 gzip plist；调用者负责提供当前账号与歌曲字段。"""
    if not isinstance(track, dict) or not track.get("persistent-id") or "cloud-id" in track:
        raise ValueError("新增单曲必须有本地持久标识，且不能指定既有云歌曲")
    if not common.get("cuid") or not common.get("troveid"):
        raise ValueError("缺少当前资料库上传标识")
    payload = {key: common[key] for key in COMMON_FIELDS if key in common}
    payload.update({"incremental": True, "cloud-incremental-update": True,
                    "persistent-library-id": library_template["persistent-library-id"],
                    "itre": library_template["itre"], "tracks": [dict(track)]})
    xml = plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False)
    xml = b"".join(line for line in xml.splitlines(keepends=True) if not line.startswith(b"<!DOCTYPE plist"))
    return {"preformatted-data": gzip.compress(xml, mtime=0)}
