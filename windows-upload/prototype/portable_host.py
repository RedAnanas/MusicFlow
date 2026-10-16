"""离线来宾的最小跨平台宿主接口；不加载 Windows DLL 或读取回放记录。"""
import ctypes
import os
import string
import struct
import unicodedata


def read_input(pointer, length, wide=False):
    unit = 2 if wide else 1
    if length == -1:
        length = 0
        while ctypes.string_at(ctypes.addressof(pointer) + length * unit, unit) != bytes(unit):
            length += 1
            assert length < 1048576
        length += 1
    assert 0 <= length <= 1048576
    return ctypes.string_at(pointer, length * unit)


def put_output(pointer, capacity, raw, wide=False):
    required = len(raw) // (2 if wide else 1)
    if not capacity:
        return required
    if capacity < required:
        return 0
    ctypes.memmove(pointer, raw, len(raw))
    return required


def decode_1252(raw):
    return ''.join(bytes([value]).decode('cp1252') if value not in (129, 141, 143, 144, 157) else chr(value) for value in raw)


def decode_936(raw):
    # Windows CP936 的单字节扩展；其余双字节序列由标准 GBK 编解码器处理。
    output = []
    offset = 0
    while offset < len(raw):
        value = raw[offset]
        if value < 128 or value in (128, 255):
            output.append('€' if value == 128 else '\uf8f5' if value == 255 else chr(value))
            offset += 1
        else:
            output.append(raw[offset:offset + 2].decode('gbk'))
            offset += 2
    return ''.join(output)


def character_flags(character):
    # shortcut: 仅验证 CRT 初始化实际使用的字符集；扩展输入前需增加原生对照。
    category = unicodedata.category(character)
    flags = 0x200 if category != 'Cn' else 0
    flags |= 1 if character.isupper() else 0
    flags |= 2 if character.islower() else 0
    flags |= 4 if category == 'Nd' else 0
    flags |= 8 if character.isspace() and character not in '\x1c\x1d\x1e\x1f' else 0
    flags |= 0x10 if character in string.punctuation or category.startswith('P') else 0
    flags |= 0x20 if category == 'Cc' else 0
    flags |= 0x40 if character == '\t' or category == 'Zs' else 0
    flags |= 0x80 if character in string.hexdigits else 0
    flags |= 0x100 if character.isalpha() else 0
    return flags


class Function:
    def __init__(self, name):
        self.name = name

    def __call__(self, *args):
        name = self.name
        if name == 'GetACP':
            return 936
        if name == 'GetOEMCP':
            return 437
        if name == 'AreFileApisANSI':
            return 1
        if name in ('GetSystemInfo', 'GetNativeSystemInfo'):
            count = min(os.cpu_count() or 1, 64)
            raw = struct.pack('<HHIQQQIIIHH', 9, 0, 4096, 0x10000, 0x7ffffffeffff,
                              (1 << count) - 1, count, 8664, 65536, 6, 0)
            assert len(raw) == 48
            ctypes.memmove(args[0], raw, 48)
            return None
        if name == 'GetCPInfo':
            assert args[0] in (0, 936)
            ctypes.memmove(args[1], struct.pack('<I', 2) + b'?\0\x81\xfe' + bytes(12), 20)
            return 1
        if name == 'MultiByteToWideChar':
            page, flags, source, length, destination, capacity = args
            assert page in (0, 936, 1252, 65001) and flags in (0, 1, 8)
            raw = read_input(source, length)
            if page == 65001:
                text = raw.decode('utf-8', errors='strict' if flags & 8 else 'replace')
            elif page in (0, 936):
                text = decode_936(raw)
            else:
                text = decode_1252(raw)
            return put_output(destination, capacity, text.encode('utf-16-le'), True)
        if name == 'WideCharToMultiByte':
            page, flags, source, length, destination, capacity, default, used = args
            assert page in (0, 936, 1252, 65001) and flags == 0 and default is None
            text = read_input(source, length, True).decode('utf-16-le')
            encoding = 'utf-8' if page == 65001 else 'gbk' if page in (0, 936) else 'cp1252'
            try:
                raw = b''.join(b'\x80' if character == '€' else b'\xff' if character == '\uf8f5' else character.encode(encoding) for character in text) if page in (0, 936) else text.encode(encoding)
                replaced = 0
            except UnicodeEncodeError:
                raw = text.encode(encoding, errors='replace')
                replaced = 1
            if used:
                ctypes.memmove(used, struct.pack('<I', replaced), 4)
            return put_output(destination, capacity, raw)
        if name == 'LCMapStringEx':
            locale, flags, source, length, destination, capacity, version, reserved, handle = args
            assert locale in (None, '', 'en-US', 'zh-CN') and flags in (0x100, 0x200)
            assert version is None and reserved is None and handle == 0
            text = read_input(source, length, True).decode('utf-16-le')
            text = text.lower() if flags == 0x100 else text.upper()
            return put_output(destination, capacity, text.encode('utf-16-le'), True)
        if name == 'GetStringTypeW':
            kind, source, length, destination = args
            assert kind == 1
            text = read_input(source, length, True).decode('utf-16-le')
            raw = b''.join(struct.pack('<H', character_flags(character)) for character in text)
            ctypes.memmove(destination, raw, len(raw))
            return 1
        if name == 'WSAStartup':
            assert args[0] == 0x202
            # 仅声明来宾 Winsock 版本；真实网络由 Python HTTP 客户端负责。
            ctypes.memmove(args[1], struct.pack('<HH', 0x202, 0x202) + bytes(404), 408)
            return 0
        raise AssertionError(f'未实现宿主接口: {name}')


EXPORTS = set('FlsAlloc FlsFree FlsGetValue FlsSetValue InitializeCriticalSectionEx CreateSemaphoreExW SetThreadStackGuarantee CreateThreadpoolTimer SetThreadpoolTimer WaitForThreadpoolTimerCallbacks CloseThreadpoolTimer CreateThreadpoolWait SetThreadpoolWait CloseThreadpoolWait FlushProcessWriteBuffers FreeLibraryWhenCallbackReturns GetCurrentProcessorNumber GetLogicalProcessorInformation CreateSymbolicLinkW SetDefaultDllDirectories EnumSystemLocalesEx CompareStringEx GetDateFormatEx GetLocaleInfoEx GetTimeFormatEx GetUserDefaultLocaleName IsValidLocaleName LCMapStringEx GetCurrentPackageId RtlCaptureStackBackTrace'.split())
EXPORTS.add('AreFileApisANSI')


class Kernel:
    def __getattr__(self, name):
        return Function(name)


class Module:
    def __init__(self, name, **kwargs):
        assert name in ('kernel32', 'api-ms-win-core-synch-l1-2-0', 'api-ms-win-core-fibers-l1-1-1', 'api-ms-win-core-localization-l1-2-1') and kwargs == {'winmode': 0x800}

    def __getattr__(self, name):
        if name not in EXPORTS:
            raise AttributeError(name)
        return Function(name)


assert decode_1252(b'A\x80') == 'A€'
assert character_flags('A') == 0x381
assert character_flags('9') == 0x284



class HostAPI:
    """单个来宾使用的宿主接口，不改写 ctypes 的全局状态。"""

    def __init__(self):
        self.kernel32 = Kernel()
        self.ws2_32 = Kernel()

    load_library = Module
