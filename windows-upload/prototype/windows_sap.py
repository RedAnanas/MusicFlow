"""受控仿真 Windows SAP 与音频算法；账号授权由单独的首次授权步骤提供。"""

import hashlib
import math
import ctypes
from pathlib import Path
import struct
import time
import os
import plistlib
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    """握手数据只发送到已确认的服务端，不跟随重定向。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

import pefile
from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.x86_const import (
    UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9,
    UC_X86_REG_RSP, UC_X86_REG_RIP, UC_X86_REG_RAX, UC_X86_REG_GS_BASE,
    UC_X86_REG_XMM0, UC_X86_REG_XMM1,
)


TARGET = Path(os.environ.get("MUSICFLOW_APPLE_BINARY", Path(__file__).resolve().parents[1] / ".tools/targets/AMPLibraryAgent.exe"))
EXPECTED = "ef493424c5768e8f5ffaf182463bee367ec68fffe1d886c06302a83ae7d427f3"
CORE_FP_HASH = "4cf0c86e5ba6b94c9a51fdbbec7104857fc5b7955fb09df663755362703f151e"
SDK_IMAGES = {'gnsdk_manager.dll': (6710886400, 'c51ce56f5afe11ebc1cc7e4d5ab747ace35f3990056f44bec767686ca13cfef6'), 'gnsdk_dsp.dll': (6979321856, 'b0fd7578afe2b2eb47e9b51dee89d79b78cb9a34fb3985c5a1f65b662316628f')}
STACK = 0x200000000
SCRATCH = 0x210000000
IMPORTS = 0x220000000
RETURN = IMPORTS + 0x10000
TEB = 0x230000000
HEAP = 0x240000000
HEAP_SIZE = 0x2000000


def _open(handshake, native_task=None, sdk_directory=None):
    if os.name == "nt":
        kernel32, load_library = ctypes.windll.kernel32, ctypes.WinDLL
        winsock = ctypes.windll.ws2_32
    else:
        from prototype.portable_host import HostAPI
        host = HostAPI()
        kernel32, load_library = host.kernel32, host.load_library
        winsock = host.ws2_32
    sdk_root = Path(sdk_directory) if sdk_directory is not None else TARGET.parent
    sdk_images = SDK_IMAGES if sdk_directory is not None else {}
    opener = build_opener(ProxyHandler({}), NoRedirect())
    binary = TARGET.read_bytes()
    if hashlib.sha256(binary).hexdigest() != EXPECTED:
        raise RuntimeError("目标版本不一致，禁止复用函数偏移")
    pe = pefile.PE(data=binary)
    base = pe.OPTIONAL_HEADER.ImageBase
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    uc.mem_write(base, pe.get_memory_mapped_image())
    uc.mem_map(STACK, 0x100000)
    uc.mem_map(SCRATCH, 0x10000)
    uc.mem_map(IMPORTS, 0x20000)
    # REA 已确认 __chkstk 在 GS:[0x10] 读取当前栈下界。
    uc.mem_map(TEB, 0x1000)
    uc.mem_write(TEB + 8, struct.pack("<QQ", STACK + 0x100000, STACK))
    if native_task is not None:
        # 音频算法包含 MSVC 延迟初始化静态变量，需要实际 PE 的 TLS 模板。
        tls = pe.DIRECTORY_ENTRY_TLS.struct
        tls_array, tls_block = TEB + 0x100, TEB + 0x200
        template = pe.get_data(tls.StartAddressOfRawData - base,
                               tls.EndAddressOfRawData - tls.StartAddressOfRawData)
        uc.mem_write(tls_block, template + bytes(tls.SizeOfZeroFill))
        uc.mem_write(tls_array, struct.pack("<Q", tls_block))
        uc.mem_write(TEB + 0x58, struct.pack("<Q", tls_array))
        uc.mem_write(tls.AddressOfIndex, struct.pack("<I", 0))
    uc.reg_write(UC_X86_REG_GS_BASE, TEB)
    uc.mem_map(HEAP, HEAP_SIZE)
    allocations = {}
    tls_slots = {}
    semaphores = {}
    guest_crypto_created = False
    heap_next = HEAP
    mutexes = set()
    events = {}
    critical_sections = {}
    srw_locks = set()
    fiber_slots = {}
    last_error = 0
    virtual_next = 0x250000000
    virtual_regions = {}
    random_providers = set()
    imports = {}
    modules = {}
    system_modules = {}

    def wire_imports(image):
        for dll in getattr(image, "DIRECTORY_ENTRY_IMPORT", []):
            for item in dll.imports:
                address = IMPORTS + len(imports) * 16
                if address >= RETURN:
                    raise RuntimeError("导入桩超过诊断容量")
                name = item.name.decode(errors="replace") if item.name else f"ordinal:{item.ordinal}"
                imports[address] = dll.dll.decode() + "!" + name
                uc.mem_write(item.address, struct.pack("<Q", address))
                uc.mem_write(address, b"\xc3")

    def cstring(address):
        return bytes(uc.mem_read(address, 260)).split(b"\0", 1)[0].decode(errors="replace")

    wire_imports(pe)
    data = TARGET.with_name("CoreFP.dll").read_bytes()
    if hashlib.sha256(data).hexdigest() != CORE_FP_HASH:
        raise RuntimeError("CoreFP 版本不一致")
    corefp = pefile.PE(data=data)
    corefp_base = corefp.OPTIONAL_HEADER.ImageBase
    uc.mem_map(corefp_base, (corefp.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    uc.mem_write(corefp_base, corefp.get_memory_mapped_image())
    wire_imports(corefp)
    modules[corefp_base] = {entry.name.decode(): corefp_base + entry.address
                           for entry in corefp.DIRECTORY_ENTRY_EXPORT.symbols if entry.name}
    extra_exports = {}
    extra_images = []
    for filename, (image_base, digest) in sdk_images.items():
        raw = (sdk_root / filename).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        image = pefile.PE(data=raw)
        image.relocate_image(image_base)
        extra_images.append(image)
        uc.mem_map(image_base, (image.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
        uc.mem_write(image_base, image.get_memory_mapped_image())
        wire_imports(image)
        for export in image.DIRECTORY_ENTRY_EXPORT.symbols:
            extra_exports[filename + "!ordinal:" + str(export.ordinal)] = image_base + export.address
            if export.name:
                extra_exports[filename + "!" + export.name.decode()] = image_base + export.address
    # SDK 包含数据导出；IAT 必须指向真实数据/代码地址，不能一律接函数桩。
    for image in [pe, corefp, *extra_images]:
        for dll in getattr(image, "DIRECTORY_ENTRY_IMPORT", []):
            module_name = dll.dll.decode().lower()
            if module_name not in sdk_images:
                continue
            for item in dll.imports:
                name = item.name.decode() if item.name else "ordinal:" + str(item.ordinal)
                target = extra_exports[module_name + "!" + name]
                uc.mem_write(item.address, struct.pack("<Q", target))
    stopped = {}

    def imported(machine, address, size, _):
        nonlocal heap_next, last_error, virtual_next, guest_crypto_created
        symbol = imports.get(address, "unknown")
        api = symbol.rsplit("!", 1)[-1]
        dll_name, _, function_name = symbol.partition("!")
        if api == "CryptAcquireContextW":
            flags = struct.unpack("<I", machine.mem_read(machine.reg_read(UC_X86_REG_RSP) + 0x28, 4))[0]
            if flags in (0, 8) and machine.reg_read(UC_X86_REG_RDX) == 0 and machine.reg_read(UC_X86_REG_R9) == 1:
                # 来宾默认密钥容器仅在内存中存在，不读取宿主用户密钥。
                if not guest_crypto_created and flags == 0:
                    last_error = 0x80090016
                    machine.reg_write(UC_X86_REG_RAX, 0)
                    return
                if guest_crypto_created and flags == 8:
                    last_error = 0x8009000f
                    machine.reg_write(UC_X86_REG_RAX, 0)
                    return
                guest_crypto_created = True
                handle = 0x600 + len(random_providers)
                random_providers.add(handle)
                machine.mem_write(machine.reg_read(UC_X86_REG_RCX), struct.pack("<Q", handle))
                machine.reg_write(UC_X86_REG_RAX, 1)
                return
        if api in ("EncodePointer", "DecodePointer"):
            machine.reg_write(UC_X86_REG_RAX, machine.reg_read(UC_X86_REG_RCX) ^ 0x6a09e667f3bcc909)
            return
        if api == "GetEnvironmentVariableW":
            # 封闭来宾不继承宿主环境变量。
            last_error = 203
            machine.reg_write(UC_X86_REG_RAX, 0)
            return
        if api == "WSAStartup":
            buffer = ctypes.create_string_buffer(408)
            function = winsock.WSAStartup
            function.argtypes = [ctypes.c_ushort, ctypes.c_void_p]
            result = function(machine.reg_read(UC_X86_REG_RCX), buffer)
            assert result == 0
            machine.mem_write(machine.reg_read(UC_X86_REG_RDX), buffer.raw)
            machine.reg_write(UC_X86_REG_RAX, result)
            return
        if api == "CreateSemaphoreW":
            assert machine.reg_read(UC_X86_REG_RCX) == 0 and machine.reg_read(UC_X86_REG_R9) == 0
            count, maximum = machine.reg_read(UC_X86_REG_RDX), machine.reg_read(UC_X86_REG_R8)
            assert 0 <= count <= maximum <= 0x7fffffff
            handle = 0x8000 + len(semaphores)
            semaphores[handle] = [count, maximum]
            machine.reg_write(UC_X86_REG_RAX, handle)
            return
        if api in ("WaitForSingleObject", "ReleaseSemaphore", "CloseHandle") and machine.reg_read(UC_X86_REG_RCX) in semaphores:
            handle = machine.reg_read(UC_X86_REG_RCX)
            count, maximum = semaphores[handle]
            if api == "WaitForSingleObject":
                assert count > 0, "单线程探针将阻塞，停止执行"
                semaphores[handle][0] -= 1
                machine.reg_write(UC_X86_REG_RAX, 0)
            elif api == "ReleaseSemaphore":
                increment = machine.reg_read(UC_X86_REG_RDX)
                previous = machine.reg_read(UC_X86_REG_R8)
                assert 0 < increment <= maximum - count
                if previous:
                    machine.mem_write(previous, struct.pack("<I", count))
                semaphores[handle][0] += increment
                machine.reg_write(UC_X86_REG_RAX, 1)
            else:
                del semaphores[handle]
                machine.reg_write(UC_X86_REG_RAX, 1)
            return
        if api == "TlsAlloc":
            index = next(i for i in range(1088) if i not in tls_slots)
            tls_slots[index] = 0
            machine.reg_write(UC_X86_REG_RAX, index)
            return
        if api in ("TlsGetValue", "TlsSetValue", "TlsFree"):
            index = machine.reg_read(UC_X86_REG_RCX)
            assert index in tls_slots, "探针访问未分配的TLS槽"
            if api == "TlsGetValue":
                last_error = 0
                machine.reg_write(UC_X86_REG_RAX, tls_slots[index])
            elif api == "TlsSetValue":
                tls_slots[index] = machine.reg_read(UC_X86_REG_RDX)
                machine.reg_write(UC_X86_REG_RAX, 1)
            else:
                del tls_slots[index]
                machine.reg_write(UC_X86_REG_RAX, 1)
            return
        if api == "HeapSize":
            assert machine.reg_read(UC_X86_REG_RCX) == 0x200
            pointer = machine.reg_read(UC_X86_REG_R8)
            assert pointer in allocations, "探针查询未知堆块"
            machine.reg_write(UC_X86_REG_RAX, allocations[pointer])
            return
        if api == "HeapReAlloc":
            assert machine.reg_read(UC_X86_REG_RCX) == 0x200
            flags = machine.reg_read(UC_X86_REG_RDX)
            pointer = machine.reg_read(UC_X86_REG_R8)
            length = machine.reg_read(UC_X86_REG_R9)
            assert flags & ~0x18 == 0 and pointer in allocations
            allocation = max(16, (length + 15) & ~15)
            if flags & 0x10:
                machine.reg_write(UC_X86_REG_RAX, pointer if allocation <= allocations[pointer] else 0)
                return
            assert heap_next + allocation <= HEAP + HEAP_SIZE, "探针堆耗尽"
            machine.mem_write(heap_next, bytes(machine.mem_read(pointer, min(allocations[pointer], allocation))))
            allocations[heap_next] = allocation
            del allocations[pointer]
            machine.reg_write(UC_X86_REG_RAX, heap_next)
            heap_next += allocation
            return
        if api == "GetModuleHandleW":
            pointer = machine.reg_read(UC_X86_REG_RCX)
            if not pointer:
                machine.reg_write(UC_X86_REG_RAX, base)
                return
            name = bytes(machine.mem_read(pointer, 520)).decode("utf-16-le").split("\0", 1)[0].lower()
            if name in sdk_images:
                machine.reg_write(UC_X86_REG_RAX, sdk_images[name][0])
                return
            if name in ("kernel32", "kernel32.dll"):
                system_modules[0x400] = ("kernel32.dll", load_library("kernel32", winmode=0x800))
                machine.reg_write(UC_X86_REG_RAX, 0x400)
                return
            stopped.update(reason="unknown_module", requested_library=name)
            machine.emu_stop()
            return
        if api == "LoadLibraryA" and cstring(machine.reg_read(UC_X86_REG_RCX)).lower() == "kernel32.dll":
            system_modules[0x400] = ("kernel32.dll", load_library("kernel32", winmode=0x800))
            machine.reg_write(UC_X86_REG_RAX, 0x400)
            return
        if api == "LoadLibraryA" and cstring(machine.reg_read(UC_X86_REG_RCX)).lower() == "dbghelp.dll":
            # 封闭来宾没有调试帮助库，返回真实缺失语义，不伪造其导出。
            last_error = 126
            machine.reg_write(UC_X86_REG_RAX, 0)
            return
        target = extra_exports.get(dll_name.lower() + "!" + function_name)
        if api == "GetModuleFileNameA":
            handle = machine.reg_read(UC_X86_REG_RCX)
            names = {image_base: name for name, (image_base, _) in sdk_images.items()}
            names.update({0: "AMPLibraryAgent.exe", base: "AMPLibraryAgent.exe"})
            if handle in names:
                raw = ("C:\\WindowsSapProbe\\" + names[handle]).encode("ascii")
                capacity = machine.reg_read(UC_X86_REG_R8) & 0xffffffff
                assert capacity > len(raw), "探针路径缓冲区不足"
                machine.mem_write(machine.reg_read(UC_X86_REG_RDX), raw + b"\0")
                machine.reg_write(UC_X86_REG_RAX, len(raw))
                return
        if target is not None:
            machine.reg_write(UC_X86_REG_RIP, target)
            return
        if api == "AcquireSRWLockExclusive":
            lock = machine.reg_read(UC_X86_REG_RCX)
            if lock in srw_locks:
                raise RuntimeError("单线程音频仿真出现锁争用")
            srw_locks.add(lock)
            return
        if api == "ReleaseSRWLockExclusive":
            lock = machine.reg_read(UC_X86_REG_RCX)
            if lock not in srw_locks:
                raise RuntimeError("音频仿真释放了未持有的锁")
            srw_locks.remove(lock)
            return
        if api == "WakeAllConditionVariable":
            return
        if api == "lroundf":
            value = struct.unpack("<f", machine.reg_read(UC_X86_REG_XMM0).to_bytes(16, "little")[:4])[0]
            rounded = math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)
            machine.reg_write(UC_X86_REG_RAX, rounded & 0xffffffff)
            return
        math_name = api[:-1] if api.endswith("f") else api
        if math_name in ("cos", "sin", "sqrt", "floor", "ceil", "log", "log10", "exp", "pow", "atan2"):
            encoding = "<f" if api.endswith("f") else "<d"
            def xmm_value(register):
                return struct.unpack(encoding, machine.reg_read(register).to_bytes(16, "little")[:struct.calcsize(encoding)])[0]
            args = [xmm_value(UC_X86_REG_XMM0)]
            if math_name in ("pow", "atan2"):
                args.append(xmm_value(UC_X86_REG_XMM1))
            value = float(getattr(math, math_name)(*args))
            machine.reg_write(UC_X86_REG_XMM0, int.from_bytes(struct.pack(encoding, value), "little"))
            return
        if api in ("memset", "memcpy", "memmove"):
            destination = machine.reg_read(UC_X86_REG_RCX)
            source = machine.reg_read(UC_X86_REG_RDX)
            length = machine.reg_read(UC_X86_REG_R8)
            if length > HEAP_SIZE:
                raise RuntimeError("原生算法内存操作超出探测容量")
            if length:
                data = bytes([source & 255]) * length if api == "memset" else bytes(machine.mem_read(source, length))
                machine.mem_write(destination, data)
            machine.reg_write(UC_X86_REG_RAX, destination)
            return
        if api in ("CryptAcquireContextA", "CryptAcquireContextW"):
            flags = struct.unpack("<I", machine.mem_read(machine.reg_read(UC_X86_REG_RSP) + 0x28, 4))[0]
            if flags & 0xf0000000 == 0xf0000000:
                handle = 0x600 + len(random_providers)
                random_providers.add(handle)
                machine.mem_write(machine.reg_read(UC_X86_REG_RCX), struct.pack("<Q", handle))
                machine.reg_write(UC_X86_REG_RAX, 1)
                return
        if api == "CryptGenRandom":
            length = machine.reg_read(UC_X86_REG_RDX) & 0xffffffff
            if machine.reg_read(UC_X86_REG_RCX) in random_providers and length <= 0x100000:
                machine.mem_write(machine.reg_read(UC_X86_REG_R8), os.urandom(length))
                machine.reg_write(UC_X86_REG_RAX, 1)
                return
        if api == "CryptReleaseContext" and machine.reg_read(UC_X86_REG_RCX) in random_providers:
            random_providers.remove(machine.reg_read(UC_X86_REG_RCX))
            machine.reg_write(UC_X86_REG_RAX, 1)
            return
        if api == "VirtualAlloc":
            requested = machine.reg_read(UC_X86_REG_RCX)
            length = machine.reg_read(UC_X86_REG_RDX)
            flags = machine.reg_read(UC_X86_REG_R8) & 0xffffffff
            if not requested and 0 < length <= 0x4000000 and flags in (0x1000, 0x2000, 0x3000):
                size = (length + 4095) & ~4095
                machine.mem_map(virtual_next, size)
                virtual_regions[virtual_next] = size
                machine.reg_write(UC_X86_REG_RAX, virtual_next)
                virtual_next += size + 0x10000
                return
        if api == "VirtualFree":
            pointer = machine.reg_read(UC_X86_REG_RCX)
            if pointer in virtual_regions and machine.reg_read(UC_X86_REG_R8) == 0x8000:
                machine.mem_unmap(pointer, virtual_regions.pop(pointer))
                machine.reg_write(UC_X86_REG_RAX, 1)
                return
        if api in ("GetSystemInfo", "GetNativeSystemInfo"):
            buffer = ctypes.create_string_buffer(48)
            getattr(kernel32, api)(buffer)
            machine.mem_write(machine.reg_read(UC_X86_REG_RCX), buffer.raw)
            return
        if api == "GetModuleFileNameW":
            handle = machine.reg_read(UC_X86_REG_RCX)
            filename = "CoreFP.dll" if handle == corefp_base else "AMPLibraryAgent.exe"
            name = "C:\\WindowsSapProbe\\" + filename
            capacity = machine.reg_read(UC_X86_REG_R8) & 0xffffffff
            if capacity > len(name):
                machine.mem_write(machine.reg_read(UC_X86_REG_RDX), (name + "\0").encode("utf-16-le"))
                machine.reg_write(UC_X86_REG_RAX, len(name))
                return
        if api == "InitializeSListHead":
            pointer = machine.reg_read(UC_X86_REG_RCX)
            if pointer % 16 == 0:
                machine.mem_write(pointer, bytes(16))
                return
        if api == "WideCharToMultiByte":
            sp_now = machine.reg_read(UC_X86_REG_RSP)
            destination, capacity, default_char, used_default = struct.unpack("<QQQQ", machine.mem_read(sp_now + 0x28, 32))
            capacity &= 0xffffffff
            length = ctypes.c_int(machine.reg_read(UC_X86_REG_R9) & 0xffffffff).value
            source = machine.reg_read(UC_X86_REG_R8)
            if length == -1:
                raw = bytes(machine.mem_read(source, 520))
                size = next((i + 2 for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\0\0"), 520)
                raw = raw[:size]
            elif 0 <= length <= 0x100000:
                raw = bytes(machine.mem_read(source, length * 2))
            else:
                raw = None
            if raw is None or capacity > 0x100000 or default_char:
                stopped.update(reason="unsupported_conversion")
                machine.emu_stop()
                return
            input_buffer = ctypes.create_string_buffer(raw)
            output_buffer = ctypes.create_string_buffer(capacity) if capacity else None
            used = ctypes.c_int()
            convert = kernel32.WideCharToMultiByte
            convert.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
            result = convert(machine.reg_read(UC_X86_REG_RCX), machine.reg_read(UC_X86_REG_RDX), input_buffer, length, output_buffer, capacity, None, ctypes.byref(used) if used_default else None)
            if result and capacity:
                machine.mem_write(destination, output_buffer.raw[:result])
            if used_default:
                machine.mem_write(used_default, struct.pack("<i", used.value))
            machine.reg_write(UC_X86_REG_RAX, result)
            return
        if api == "LCMapStringEx":
            sp_now = machine.reg_read(UC_X86_REG_RSP)
            destination, capacity, version, reserved, sort_handle = struct.unpack("<QQQQQ", machine.mem_read(sp_now + 0x28, 40))
            capacity &= 0xffffffff
            length = ctypes.c_int(machine.reg_read(UC_X86_REG_R9) & 0xffffffff).value
            source = machine.reg_read(UC_X86_REG_R8)
            locale_pointer = machine.reg_read(UC_X86_REG_RCX)
            locale = None if not locale_pointer else bytes(machine.mem_read(locale_pointer, 170)).decode("utf-16-le").split("\0", 1)[0]
            if length < 0:
                raw = bytes(machine.mem_read(source, 520))
                size = next((i + 2 for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\0\0"), 520)
                raw = raw[:size]
            elif length <= 0x100000:
                raw = bytes(machine.mem_read(source, length * 2))
            else:
                raw = None
            if raw is None or capacity > 0x100000 or version or reserved or sort_handle:
                stopped.update(reason="unsupported_locale_mapping")
                machine.emu_stop()
                return
            input_buffer = ctypes.create_string_buffer(raw)
            output_buffer = ctypes.create_string_buffer(capacity * 2) if capacity else None
            convert = kernel32.LCMapStringEx
            convert.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t]
            flags = machine.reg_read(UC_X86_REG_RDX) & 0xffffffff
            result = convert(locale, flags, input_buffer, length, output_buffer, capacity, None, None, 0)
            if result and capacity:
                machine.mem_write(destination, output_buffer.raw[:result if flags & 0x400 else result * 2])
            machine.reg_write(UC_X86_REG_RAX, result)
            return
        if api == "GetStringTypeW":
            length = ctypes.c_int(machine.reg_read(UC_X86_REG_R8) & 0xffffffff).value
            source = machine.reg_read(UC_X86_REG_RDX)
            if length == -1:
                raw = bytes(machine.mem_read(source, 520))
                length = next((i // 2 + 1 for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\0\0"), 260)
            if not 0 <= length <= 0x100000:
                stopped.update(reason="conversion_limit")
                machine.emu_stop()
                return
            input_buffer = ctypes.create_string_buffer(bytes(machine.mem_read(source, length * 2)))
            output_buffer = ctypes.create_string_buffer(length * 2)
            classify = kernel32.GetStringTypeW
            classify.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            result = classify(machine.reg_read(UC_X86_REG_RCX), input_buffer, length, output_buffer)
            if result:
                machine.mem_write(machine.reg_read(UC_X86_REG_R9), output_buffer.raw)
            machine.reg_write(UC_X86_REG_RAX, result)
            return
        if api in ("GetACP", "GetOEMCP", "AreFileApisANSI"):
            machine.reg_write(UC_X86_REG_RAX, getattr(kernel32, api)())
            return
        if api == "GetCPInfo":
            buffer = ctypes.create_string_buffer(20)
            result = kernel32.GetCPInfo(machine.reg_read(UC_X86_REG_RCX), buffer)
            if result:
                machine.mem_write(machine.reg_read(UC_X86_REG_RDX), buffer.raw)
            machine.reg_write(UC_X86_REG_RAX, result)
            return
        if api == "MultiByteToWideChar":
            length = ctypes.c_int(machine.reg_read(UC_X86_REG_R9) & 0xffffffff).value
            source = machine.reg_read(UC_X86_REG_R8)
            sp_now = machine.reg_read(UC_X86_REG_RSP)
            destination, capacity = struct.unpack("<QQ", machine.mem_read(sp_now + 0x28, 16))
            capacity &= 0xffffffff
            if length == -1:
                raw = bytes(machine.mem_read(source, 260)).split(b"\0", 1)[0] + b"\0"
            elif 0 <= length <= 0x100000:
                raw = bytes(machine.mem_read(source, length))
            else:
                stopped.update(reason="conversion_limit")
                machine.emu_stop()
                return
            if capacity > 0x100000:
                stopped.update(reason="conversion_limit")
                machine.emu_stop()
                return
            input_buffer = ctypes.create_string_buffer(raw)
            output_buffer = ctypes.create_string_buffer(capacity * 2) if capacity else None
            convert = kernel32.MultiByteToWideChar
            convert.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
            result = convert(machine.reg_read(UC_X86_REG_RCX), machine.reg_read(UC_X86_REG_RDX), input_buffer, length, output_buffer, capacity)
            if result and capacity:
                machine.mem_write(destination, output_buffer.raw[:result * 2])
            machine.reg_write(UC_X86_REG_RAX, result)
            return
        if api == "GetStdHandle":
            # 仿真进程不连接宿主控制台，等价于无可用标准句柄。
            machine.reg_write(UC_X86_REG_RAX, 0xffffffffffffffff)
            return
        if api == "GetCommandLineA":
            machine.mem_write(SCRATCH + 0x7000, b"windows-sap-probe\0")
            machine.reg_write(UC_X86_REG_RAX, SCRATCH + 0x7000)
            return
        if api == "GetStartupInfoW":
            pointer = machine.reg_read(UC_X86_REG_RCX)
            machine.mem_write(pointer, struct.pack("<I", 104) + bytes(100))
            return
        if api in ("GetCommandLineW", "GetEnvironmentStringsW"):
            pointer = SCRATCH + (0x5000 if api == "GetCommandLineW" else 0x6000)
            machine.mem_write(pointer, ("windows-sap-probe\0" if api == "GetCommandLineW" else "\0\0").encode("utf-16-le"))
            machine.reg_write(UC_X86_REG_RAX, pointer)
            return
        if api == "FreeEnvironmentStringsW":
            machine.reg_write(UC_X86_REG_RAX, 1)
            return
        if api == "FlsAlloc":
            index = len(fiber_slots)
            fiber_slots[index] = 0
            machine.reg_write(UC_X86_REG_RAX, index)
            return
        if api in ("FlsGetValue", "FlsSetValue"):
            index = machine.reg_read(UC_X86_REG_RCX)
            if index in fiber_slots:
                if api == "FlsGetValue":
                    machine.reg_write(UC_X86_REG_RAX, fiber_slots[index])
                else:
                    fiber_slots[index] = machine.reg_read(UC_X86_REG_RDX)
                    machine.reg_write(UC_X86_REG_RAX, 1)
                last_error = 0
                return
        if api in ("GetLastError", "SetLastError"):
            if api == "GetLastError":
                machine.reg_write(UC_X86_REG_RAX, last_error)
            else:
                last_error = machine.reg_read(UC_X86_REG_RCX) & 0xffffffff
            return
        if api in ("InitializeCriticalSectionEx", "InitializeCriticalSectionAndSpinCount", "InitializeCriticalSection"):
            pointer = machine.reg_read(UC_X86_REG_RCX)
            machine.mem_write(pointer, bytes(8) + struct.pack("<iIQQQ", -1, 0, 0, 0, 0))
            critical_sections[pointer] = 0
            machine.reg_write(UC_X86_REG_RAX, 1)
            return
        if api in ("EnterCriticalSection", "LeaveCriticalSection", "DeleteCriticalSection"):
            pointer = machine.reg_read(UC_X86_REG_RCX)
            if pointer in critical_sections:
                if api == "EnterCriticalSection":
                    critical_sections[pointer] += 1
                    return
                if api == "LeaveCriticalSection" and critical_sections[pointer] > 0:
                    critical_sections[pointer] -= 1
                    return
                if api == "DeleteCriticalSection" and critical_sections[pointer] == 0:
                    del critical_sections[pointer]
                    return
        if api == "LoadLibraryExW":
            raw = bytes(machine.mem_read(machine.reg_read(UC_X86_REG_RCX), 520))
            name = raw.decode("utf-16-le", errors="replace").split("\0", 1)[0]
            if (name == "kernel32" or name.startswith("api-ms-win-core-")) and all(c.isalnum() or c in "-." for c in name):
                # 只向 System32 查询 Microsoft API 集是否存在，绝不执行其未知接口。
                try:
                    module = load_library(name, winmode=0x800)
                    handle = 0x400 + len(system_modules)
                    system_modules[handle] = (name, module)
                except OSError:
                    handle = 0
                    last_error = 126
                machine.reg_write(UC_X86_REG_RAX, handle)
                return
        if api == "GetSystemTimeAsFileTime":
            machine.mem_write(machine.reg_read(UC_X86_REG_RCX), struct.pack("<Q", time.time_ns() // 100 + 116444736000000000))
            return
        if api in ("GetCurrentProcessId", "GetCurrentThreadId", "GetProcessHeap"):
            machine.reg_write(UC_X86_REG_RAX, 0x200 if api == "GetProcessHeap" else 1)
            return
        if api in ("QueryPerformanceCounter", "QueryPerformanceFrequency"):
            machine.mem_write(machine.reg_read(UC_X86_REG_RCX), struct.pack("<Q", time.monotonic_ns() if api == "QueryPerformanceCounter" else 1000000000))
            machine.reg_write(UC_X86_REG_RAX, 1)
            return
        if symbol.endswith("!LoadLibraryA") and cstring(machine.reg_read(UC_X86_REG_RCX)).lower() == "corefp.dll":
            machine.reg_write(UC_X86_REG_RAX, next(iter(modules)))
            return
        if symbol.endswith("!GetProcAddress"):
            handle = machine.reg_read(UC_X86_REG_RCX)
            name = cstring(machine.reg_read(UC_X86_REG_RDX))
            if handle in modules and name in modules[handle]:
                machine.reg_write(UC_X86_REG_RAX, modules[handle][name])
                return
            if handle in system_modules:
                module_name, module = system_modules[handle]
                if not hasattr(module, name):
                    machine.reg_write(UC_X86_REG_RAX, 0)
                    last_error = 127
                    return
                stub = IMPORTS + len(imports) * 16
                if stub >= RETURN:
                    raise RuntimeError("导入桩超过诊断容量")
                imports[stub] = module_name + "!" + name
                machine.mem_write(stub, b"\xc3")
                machine.reg_write(UC_X86_REG_RAX, stub)
                return
            stopped.update(reason="unsupported_export", symbol=name)
            machine.emu_stop()
            return
        if api == "_aligned_malloc":
            length = machine.reg_read(UC_X86_REG_RCX)
            alignment = machine.reg_read(UC_X86_REG_RDX)
            if alignment < 8 or alignment & (alignment - 1):
                raise RuntimeError("原生算法请求了无效内存对齐")
            pointer = (heap_next + alignment - 1) & ~(alignment - 1)
            end = pointer + max(length, 16)
            if end > HEAP + HEAP_SIZE:
                stopped.update(reason="heap_limit")
                machine.emu_stop()
                return
            machine.reg_write(UC_X86_REG_RAX, pointer)
            heap_next = end
            return
        if api == "malloc" or (api == "HeapAlloc" and machine.reg_read(UC_X86_REG_RCX) == 0x200):
            length = machine.reg_read(UC_X86_REG_RCX if api == "malloc" else UC_X86_REG_R8)
            allocation = max(16, (length + 15) & ~15)
            if heap_next + allocation > HEAP + HEAP_SIZE:
                stopped.update(reason="heap_limit")
                machine.emu_stop()
                return
            machine.reg_write(UC_X86_REG_RAX, heap_next)
            allocations[heap_next] = allocation
            heap_next += allocation
            return
        if api in ("free", "_aligned_free"):
            return
        if api == "HeapFree" and machine.reg_read(UC_X86_REG_RCX) == 0x200:
            pointer = machine.reg_read(UC_X86_REG_R8)
            if HEAP <= pointer < heap_next:
                machine.reg_write(UC_X86_REG_RAX, 1)
                return
        # 仿真只有一个线程；这些调用仍检查句柄，不能掩盖未知依赖。
        if symbol.endswith("!CreateMutexA"):
            handle = 0x100 + len(mutexes) + len(events)
            mutexes.add(handle)
            machine.reg_write(UC_X86_REG_RAX, handle)
            return
        if api in ("CreateEventA", "CreateEventW"):
            handle = 0x100 + len(mutexes) + len(events)
            events[handle] = bool(machine.reg_read(UC_X86_REG_R8))
            machine.reg_write(UC_X86_REG_RAX, handle)
            return
        if symbol.rsplit("!", 1)[-1] in ("SetEvent", "ResetEvent"):
            handle = machine.reg_read(UC_X86_REG_RCX)
            if handle in events:
                events[handle] = symbol.endswith("!SetEvent")
                machine.reg_write(UC_X86_REG_RAX, 1)
                return
        if symbol.rsplit("!", 1)[-1] in ("WaitForSingleObject", "ReleaseMutex", "CloseHandle"):
            handle = machine.reg_read(UC_X86_REG_RCX)
            if handle in mutexes:
                machine.reg_write(UC_X86_REG_RAX, 0 if symbol.endswith("!WaitForSingleObject") else 1)
                return
        if address == RETURN:
            stopped.update(reason="returned", return_code=machine.reg_read(UC_X86_REG_RAX) & 0xffffffff)
        else:
            stopped.update(reason="unsupported_import", symbol=symbol)
            if symbol.endswith("!HeapAlloc"):
                stopped["heap_handle_initialized"] = bool(machine.reg_read(UC_X86_REG_RCX))
                stopped["allocation_bytes"] = machine.reg_read(UC_X86_REG_R8)
            if symbol.endswith("!LoadLibraryA"):
                pointer = machine.reg_read(UC_X86_REG_RCX)
                stopped["requested_library"] = cstring(pointer)
            if api == "LoadLibraryExW":
                raw = bytes(machine.mem_read(machine.reg_read(UC_X86_REG_RCX), 520))
                stopped["requested_library"] = raw.decode("utf-16-le", errors="replace").split("\0", 1)[0]
        machine.emu_stop()

    def invalid(machine, access, address, size, value, _):
        stopped.update(reason="unmapped_memory", access=access, address=hex(address), size=size,
                       instruction=hex(machine.reg_read(UC_X86_REG_RIP)))
        return False

    uc.hook_add(UC_HOOK_CODE, imported, begin=IMPORTS, end=IMPORTS + 0x1ffff)
    uc.hook_add(UC_HOOK_MEM_INVALID, invalid)
    if native_task is not None:
        # 音频算法探测复用 PE 加载器，不初始化 SAP，也不发送网络请求。
        native_sp = STACK + 0x100000 - 0x108

        def invoke(entry, *args):
            stopped.clear()
            uc.mem_write(native_sp, struct.pack("<Q", RETURN) + bytes(0x80))
            uc.reg_write(UC_X86_REG_RSP, native_sp)
            for register, value in zip((UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9), args):
                uc.reg_write(register, value)
            for index, value in enumerate(args[4:]):
                uc.mem_write(native_sp + 0x28 + index * 8, struct.pack("<Q", value))
            try:
                uc.emu_start(base + entry, RETURN, timeout=30_000_000, count=200_000_000)
            except UcError:
                if not stopped:
                    stopped.update(reason="emulator_error", instruction=hex(uc.reg_read(UC_X86_REG_RIP)))
            if uc.reg_read(UC_X86_REG_RIP) != RETURN:
                error = RuntimeError("原生音频算法未运行到返回点")
                error.native_report = dict(stopped)
                raise error
            return uc.reg_read(UC_X86_REG_RAX)

        result = native_task(uc, invoke)
        return result, None
    # 使用固定合成硬件标识，只验证初始化路径；不冒用用户设备标识。
    uc.mem_write(SCRATCH, struct.pack("<I", 6) + bytes.fromhex("020000000001") + bytes(14))
    output = SCRATCH + 0x100
    sp = STACK + 0x100000 - 0x108
    uc.mem_write(sp, struct.pack("<Q", RETURN))
    uc.reg_write(UC_X86_REG_RSP, sp)
    uc.reg_write(UC_X86_REG_RCX, corefp_base)
    uc.reg_write(UC_X86_REG_RDX, 1)
    uc.reg_write(UC_X86_REG_R8, 0)
    uc.reg_write(UC_X86_REG_R9, 0)
    stage = "corefp_dll_init"
    try:
        # 仅在虚拟机中执行 DLL 初始化；所有未知 OS 调用仍会停止。
        uc.emu_start(corefp_base + corefp.OPTIONAL_HEADER.AddressOfEntryPoint, RETURN,
                     timeout=15_000_000, count=2_000_000)
        # Unicorn 到达结束哨兵时可能在执行哨兵 hook 前返回。
        if uc.reg_read(UC_X86_REG_RIP) == RETURN and not stopped:
            stopped.update(reason="returned", return_code=uc.reg_read(UC_X86_REG_RAX) & 0xffffffff)
        if stopped.get("reason") == "returned" and stopped.get("return_code") == 1:
            stopped.clear()
            stage = "sap_create"
            uc.mem_write(sp, struct.pack("<Q", RETURN))
            uc.reg_write(UC_X86_REG_RSP, sp)
            uc.reg_write(UC_X86_REG_RCX, output)
            uc.reg_write(UC_X86_REG_RDX, SCRATCH)
            uc.reg_write(UC_X86_REG_R8, 0)
            uc.reg_write(UC_X86_REG_R9, 0)
            uc.emu_start(base + 0x5e850, RETURN, timeout=15_000_000, count=100_000_000)
            if uc.reg_read(UC_X86_REG_RIP) == RETURN and not stopped:
                stopped.update(reason="returned", return_code=uc.reg_read(UC_X86_REG_RAX) & 0xffffffff)
    except UcError as error:
        if not stopped:
            stopped.update(reason="emulator_error", error=str(error),
                           instruction=hex(uc.reg_read(UC_X86_REG_RIP)))
    if not stopped:
        stopped.update(reason="execution_limit", instruction=hex(uc.reg_read(UC_X86_REG_RIP)))
    sign_callback = None
    if handshake and stopped.get("reason") == "returned" and stopped.get("return_code") == 0:
        context = struct.unpack("<Q", uc.mem_read(output, 8))[0]
        input_address = 0x280000000
        uc.mem_map(input_address, 0x800000)
        out, out_length, flag = SCRATCH + 0x200, SCRATCH + 0x208, SCRATCH + 0x210

        def call(entry, register_args, stack_args, allow_empty=False):
            stopped.clear()
            uc.mem_write(sp, struct.pack("<Q", RETURN) + bytes(0x80))
            uc.reg_write(UC_X86_REG_RSP, sp)
            for register, value in zip((UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9), register_args):
                uc.reg_write(register, value)
            for index, value in enumerate(stack_args):
                uc.mem_write(sp + 0x28 + index * 8, struct.pack("<Q", value))
            try:
                uc.emu_start(base + entry, RETURN, timeout=30_000_000, count=1_000_000_000)
            except UcError:
                pass
            if stopped:
                return None
            if uc.reg_read(UC_X86_REG_RIP) != RETURN:
                stopped.update(reason="execution_limit", instruction=hex(uc.reg_read(UC_X86_REG_RIP)))
                return None
            rc = uc.reg_read(UC_X86_REG_RAX) & 0xffffffff
            if rc:
                stopped.update(reason="native_error", return_code=rc)
                return None
            pointer = struct.unpack("<Q", uc.mem_read(out, 8))[0]
            size = struct.unpack("<I", uc.mem_read(out_length, 4))[0]
            if allow_empty and size == 0:
                return b""
            if not pointer or not 0 < size <= 0x800000:
                stopped.update(reason="invalid_output", output_bytes=size)
                return None
            return bytes(uc.mem_read(pointer, size))

        def process(payload):
            if len(payload) > 0x800000:
                raise RuntimeError("握手输入超出诊断容量")
            uc.mem_write(input_address, payload)
            uc.mem_write(out, bytes(24))
            return call(0x9f710, (200, SCRATCH, context, input_address), (len(payload), out, out_length, flag), allow_empty=True)

        stage = "sap_handshake"
        try:
            with opener.open("https://s.mzstatic.com/sap/setupCert.plist", timeout=30) as response:
                cert = plistlib.loads(response.read())["sign-sap-setup-cert"]
            payload = process(cert)
            rounds = 0
            while payload is not None and uc.mem_read(flag, 1)[0] == 1 and rounds < 4:
                body = plistlib.dumps({"sign-sap-setup-buffer": payload})
                request = Request("https://fpinit.itunes.apple.com/v1/signSapSetup/legacy", data=body,
                                  headers={"Content-Type": "application/x-apple-plist"}, method="POST")
                with opener.open(request, timeout=30) as response:
                    server_data = plistlib.loads(response.read())["sign-sap-setup-buffer"]
                rounds += 1
                payload = process(server_data)
            if payload is not None and uc.mem_read(flag, 1)[0] == 0:
                stage = "sap_sign"

                def sign(data):
                    if not isinstance(data, bytes) or not 0 < len(data) <= 0x800000:
                        raise SapError("签名输入必须是 1 字节至 8 MiB 内的二进制请求体")
                    uc.mem_write(input_address, data)
                    uc.mem_write(out, bytes(24))
                    result = call(0x15630, (context, input_address, len(data), out), (out_length,))
                    if result is None:
                        raise SapError("Windows SAP 原生签名失败")
                    return result

                signature = sign(b"MusicFlow Windows SAP independent probe")
                if signature is not None:
                    stopped.update(reason="signed", signature_bytes=len(signature), handshake_rounds=rounds)
                    sign_callback = sign
            elif not stopped:
                stopped.update(reason="handshake_incomplete", handshake_rounds=rounds)
        except Exception as error:
            # 握手材料和地址不进入错误日志。
            stopped.update(reason="handshake_exception", error_type=type(error).__name__)
    stopped["context_created"] = bool(struct.unpack("<Q", uc.mem_read(output, 8))[0])
    stopped["account_accessed"] = False
    stopped["network_used"] = bool(handshake and stage in ("sap_handshake", "sap_sign"))
    stopped["corefp_mapped"] = bool(modules)
    stopped["stage"] = stage
    stopped["target_sha256"] = EXPECTED
    stopped["corefp_sha256"] = CORE_FP_HASH
    stopped["cloud_upload_confirmed"] = False
    return dict(stopped), sign_callback



class SapError(Exception):
    """只返回脱敏错误，不包含签名、握手材料或请求体。"""


class WindowsSapSigner:
    """复用单个仿真上下文的实验签名器；每个实例只能由一个线程调用。"""

    def __init__(self):
        self.report, self._sign = _open(True)
        if self._sign is None:
            raise SapError("Windows SAP 初始化或握手失败")

    def sign(self, payload):
        """返回原生签名二进制；调用者不得将它写入普通日志。"""
        return self._sign(payload)


def probe(handshake=False):
    """仅返回初始化和签名验证摘要，不返回签名材料。"""
    report, _ = _open(handshake)
    return report
