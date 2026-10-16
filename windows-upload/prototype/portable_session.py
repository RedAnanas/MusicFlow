"""以独立密钥保护可移植授权和检查点，不依赖 Windows DPAPI。"""

import json
import os
from pathlib import Path
import secrets
import stat
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b'MFUP1\0'
MAX_BYTES = 64 * 1024 * 1024


class PortableSessionError(Exception):
    """错误信息不包含密钥、授权或解密内容。"""


class EncryptedSessionStore:
    """密钥与密文分别保存；Windows 调用者须先限制私密目录 ACL。"""

    def __init__(self, key_path):
        self.key_path = Path(key_path)

    def _check_directory(self):
        parent = self.key_path.parent
        if parent.is_symlink() or not parent.is_dir():
            raise PortableSessionError('密钥必须位于已有私密目录')
        if os.name != 'nt':
            info = parent.stat()
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise PortableSessionError('密钥目录必须仅当前用户可访问')

    def create_key(self):
        """显式创建一次，不覆盖既有密钥。"""
        self._check_directory()
        descriptor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(secrets.token_bytes(32))
            output.flush()
            os.fsync(output.fileno())

    def _key(self):
        self._check_directory()
        try:
            if self.key_path.is_symlink():
                raise PortableSessionError('密钥不能经过符号链接')
            info = self.key_path.stat()
            if os.name != 'nt' and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
                raise PortableSessionError('密钥必须仅当前用户可读写')
            key = self.key_path.read_bytes()
            if len(key) != 32:
                raise PortableSessionError('密钥长度无效')
            return key
        except OSError:
            raise PortableSessionError('无法读取服务端密钥') from None

    def save(self, path, session):
        """原子替换检查点；随机 nonce，每次保存得到不同密文。"""
        path = Path(path)
        if path.is_symlink() or not isinstance(session, dict):
            raise PortableSessionError('会话目标或内容无效')
        raw = json.dumps(session, ensure_ascii=False).encode('utf-8')
        if len(raw) > MAX_BYTES:
            raise PortableSessionError('会话超过容量限制')
        nonce = secrets.token_bytes(12)
        encrypted = MAGIC + nonce + AESGCM(self._key()).encrypt(nonce, raw, MAGIC)
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(encrypted)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def load(self, path):
        """密文或密钥不匹配时停止，不尝试把损坏记录当作新任务。"""
        path = Path(path)
        try:
            if path.is_symlink() or path.stat().st_size > MAX_BYTES + 34:
                raise PortableSessionError('会话文件无效')
            raw = path.read_bytes()
            if not raw.startswith(MAGIC) or len(raw) < len(MAGIC) + 28:
                raise PortableSessionError('会话格式或版本无效')
            offset = len(MAGIC)
            decoded = AESGCM(self._key()).decrypt(raw[offset:offset + 12], raw[offset + 12:], MAGIC)
            session = json.loads(decoded)
            if not isinstance(session, dict):
                raise PortableSessionError('会话内容无效')
            return session
        except (OSError, ValueError, InvalidTag):
            raise PortableSessionError('会话解密失败或记录已损坏') from None
