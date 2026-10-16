"""提取已验证的单轨 M4A 音频数据，供 hash-track 计算哈希。"""

import struct


def m4a_audio_data(data):
    """按 MP4 原子长度读取 mdat；拒绝截断或多个数据原子。"""
    offset = 0
    audio = None
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError("M4A 原子头被截断")
        size, kind = struct.unpack_from(">I4s", data, offset)
        header = 8
        if size == 1:
            if len(data) - offset < 16:
                raise ValueError("M4A 扩展原子头被截断")
            size = struct.unpack_from(">Q", data, offset + 8)[0]
            header = 16
        elif size == 0:
            size = len(data) - offset
        if size < header or size > len(data) - offset:
            raise ValueError("M4A 原子长度无效")
        if kind == b"mdat":
            if audio is not None:
                raise ValueError("尚未验证多个音频数据原子的格式")
            audio = data[offset + header:offset + size]
        offset += size
    if not audio:
        raise ValueError("M4A 没有有效音频数据")
    return audio
