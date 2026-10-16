"""在容器内校验并导入加密授权，保留原密钥和任务记录。"""
import argparse
import os
from pathlib import Path
import tempfile
import time

from runtime import PRIVATE, secure_directory, exclusive_lock
from worker import identity
from prototype.portable_session import EncryptedSessionStore


def import_authorization(input_path, key_file=None):
    target_key = Path(os.environ['MUSICFLOW_UPLOAD_KEY_FILE'])
    secure_directory(target_key.parent)
    source_key = Path(key_file) if key_file is not None else target_key
    if source_key.is_symlink() or source_key.stat().st_size != 32:
        raise ValueError('导入密钥无效')
    key = source_key.read_bytes()
    if target_key.exists() and target_key.read_bytes() != key:
        raise ValueError('新密钥与现有任务密钥不同，不能覆盖')
    input_path = Path(input_path)
    if input_path.is_symlink() or input_path.stat().st_size > 64 * 1024 * 1024 + 34:
        raise ValueError('导入授权文件无效')
    # 在容器拥有的临时目录验证密文；解密内容只进入内存。
    with tempfile.TemporaryDirectory(dir=PRIVATE) as temporary:
        staging = Path(temporary)
        descriptor = os.open(staging / 'key', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(key)
        (staging / 'account').write_bytes(input_path.read_bytes())
        bundle = EncryptedSessionStore(staging / 'key').load(staging / 'account')
    current_identity = identity(bundle)
    target = PRIVATE / 'account.mfup'
    store = EncryptedSessionStore(target_key)
    if target.exists() and identity(store.load(target)) != current_identity:
        raise ValueError('授权属于不同账号或资料库，不能替换原绑定')
    if not target_key.exists():
        descriptor = os.open(target_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(key)
            output.flush()
            os.fsync(output.fileno())
    store.save(target, bundle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--key-file', type=Path, help='首次导入的独立密钥；重新授权时省略以复用现有密钥')
    args = parser.parse_args()
    if os.name == 'nt':
        parser.error('此导入入口用于 Linux 服务端')
    if not args.input.is_file():
        parser.error('导入授权文件不存在')
    secure_directory()
    pause = PRIVATE / '.pause-for-authorization'
    pause.write_text('', encoding='utf-8')
    deadline = time.monotonic() + 30
    while True:
        try:
            with exclusive_lock():
                import_authorization(args.input, args.key_file)
            break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise RuntimeError('已请求暂停，请等当前上传完成后重试；不会中断上传') from None
            time.sleep(1)
    pause.unlink(missing_ok=True)
    print('服务端授权已加密导入；原任务与密钥保留。请移走传输用的授权包和密钥副本。')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('导入未完成，请核对授权、密钥和上传进程状态；未清空原任务。')
        raise SystemExit(1) from None
