"""在独立虚拟机中生成 Windows 客户端格式的 Shazam 音频签名。"""

import struct

from prototype.windows_sap import _open, SCRATCH


def generate_signature(pcm, progress=None):
    """输入为 16 kHz 单声道 float32 PCM；每次调用创建独立算法上下文。"""
    if not pcm or len(pcm) % 4 or len(pcm) > 16000 * 4 * 3600:
        raise ValueError("签名 PCM 长度无效")

    def task(machine, invoke):
        output = SCRATCH + 0x100
        machine.mem_write(output, bytes(32))
        invoke(0xbefdb0, output, 1, 16000, 0)
        pointer = struct.unpack("<Q", machine.mem_read(output, 8))[0]
        if not pointer:
            raise ValueError("音频签名上下文创建失败")
        pcm_address = 0x280000000
        machine.mem_map(pcm_address, (len(pcm) + 4095) & ~4095)
        machine.mem_write(pcm_address, pcm)
        for offset in range(0, len(pcm), 16000 * 4):
            count = min(16000 * 4, len(pcm) - offset) // 4
            invoke(0xbeff3c, output, pcm_address + offset, count, 1)
            if progress and offset % (16000 * 4 * 15) == 0:
                progress("signature", int(100 * (offset + count * 4) / len(pcm)))
        vector = SCRATCH + 0x200
        machine.mem_write(vector, bytes(24))
        invoke(0xbeffa4, output, vector)
        begin, end, capacity = struct.unpack("<QQQ", machine.mem_read(vector, 24))
        if not begin or not begin < end <= capacity or end - begin > 1048576:
            raise ValueError("音频签名结果无效")
        return bytes(machine.mem_read(begin, end - begin))

    signature, _ = _open(False, native_task=task)
    return signature
