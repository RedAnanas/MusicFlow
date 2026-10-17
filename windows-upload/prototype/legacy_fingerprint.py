"""用已验证版本的 GNSDK 计算 partial 与 full-lowres 指纹。"""

from pathlib import Path
import struct

from prototype import windows_sap


def generate_fingerprint(pcm_path, kind, sdk_directory, progress=None):
    """输入为双声道 44.1 kHz、16 位 PCM；每次创建独立来宾。"""
    pcm_path = Path(pcm_path)
    if kind not in ('partial', 'full-lowres') or not pcm_path.is_file() or not pcm_path.stat().st_size or pcm_path.stat().st_size % 4:
        raise ValueError('旧版指纹的输入格式无效')

    def task(machine, invoke):
        main_base = 0x140000000
        for entry, base in [(0x190104f6c, 0x190000000), (0x1a0287b28, 0x1a0000000)]:
            if invoke(entry - main_base, base, 1, 0) & 0xffffffff != 1:
                raise windows_sap.SapError('指纹 DLL 初始化失败')
        output = windows_sap.SCRATCH + 0x100
        if invoke(0x190014c70 - main_base, output, 0, 0) & 0xffffffff:
            raise windows_sap.SapError('指纹管理器初始化失败')

        def pointer(address):
            return struct.unpack('<Q', machine.mem_read(address, 8))[0]

        handle = pointer(output)
        if not handle or invoke(0x1a0003c00 - main_base, handle) & 0xffffffff:
            raise windows_sap.SapError('指纹算法初始化失败')

        def call(rva, *arguments):
            if invoke(0x1a0000000 + rva - main_base, *arguments) & 0xffffffff:
                raise windows_sap.SapError('指纹算法步骤失败')

        context = windows_sap.SCRATCH + 0x300
        machine.mem_write(context, bytes(0x80))
        call(0x79d00, context + 0x20, 0, 0, 0x1a00011b0)
        call(0x2910, 17 if kind == 'full-lowres' else 1, 44100, 2, 2, 0, 0x1a00011c0, context, context + 0x18)
        engine = pointer(context + 0x18)
        if not pointer(context + 0x20) or not engine:
            raise windows_sap.SapError('指纹上下文无效')
        audio_address = 0x280000000
        machine.mem_map(audio_address, 0x40000)
        audio_size = pcm_path.stat().st_size
        with pcm_path.open('rb') as audio:
            while data := audio.read(44100 * 4):
                machine.mem_write(audio_address, data)
                machine.mem_write(context + 0x40, bytes(8))
                call(0x24f0, engine, audio_address, len(data), 0, context + 0x40)
                if progress and kind == 'full-lowres':
                    progress(kind, min(99, int(audio.tell() * 100 / audio_size)))
                if machine.mem_read(context + 0x40, 1)[0]:
                    break
        call(0x2710, engine, context + 0x40)
        call(0x79b30, pointer(context + 0x20), context + 0x48)
        count = struct.unpack('<I', machine.mem_read(context + 0x48, 4))[0]
        if not 0 < count < 1000:
            raise windows_sap.SapError('指纹结果块数量无效')
        items = windows_sap.SCRATCH + 0x1000
        for index in range(count):
            call(0x7a050, pointer(context + 0x20), index, items + index * 8)
        call(0x2cc0, engine, items, count, context + 0x50)
        result_pointer = pointer(context + 0x50)
        if not result_pointer:
            raise windows_sap.SapError('指纹结果为空')
        raw = bytes(machine.mem_read(result_pointer, 65536))
        if b'\0' not in raw:
            raise windows_sap.SapError('指纹结果超出容量')
        result = raw.split(b'\0', 1)[0]
        if not result:
            raise windows_sap.SapError('指纹结果为空')
        return result

    try:
        fingerprint, _ = windows_sap._open(False, native_task=task, sdk_directory=sdk_directory)
    except (OSError, RuntimeError, AssertionError):
        raise windows_sap.SapError('旧版指纹计算失败，请核对算法文件版本') from None
    if progress:
        progress(kind, 100)
    return fingerprint
