"""在桌面端将现有 DPAPI 授权导出为服务端可解密的授权包。"""
import argparse
import os
from pathlib import Path

from runtime import PRIVATE, secure_directory, exclusive_lock
from worker import identity
from prototype.local_session import load_session
from prototype.portable_session import EncryptedSessionStore


def export_authorization(input_path, output_directory, key_file=None):
    bundle = load_session(input_path)
    identity(bundle)
    output_directory = Path(output_directory)
    secure_directory(output_directory)
    secure_directory(output_directory / 'state')
    destination = output_directory / 'state/account.mfup'
    if destination.exists():
        raise RuntimeError('导出目标已有授权，请使用新的导出目录')
    if key_file is None:
        secure_directory(output_directory / 'keys')
        store = EncryptedSessionStore(output_directory / 'keys/store.key')
        store.create_key()
    else:
        store = EncryptedSessionStore(key_file)
    store.save(destination, bundle)
    assert store.load(destination) == bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=PRIVATE / 'apple-client-authorization.dpapi')
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--key-file', type=Path, help='重新授权时使用现有服务端密钥，不生成替代密钥')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('首次 DPAPI 授权导出需在原 Windows 用户下运行')
    with exclusive_lock():
        export_authorization(args.input, args.output_directory, args.key_file)
    print('加密授权已导出。请通过可信方式导入服务端；密钥单独保管，不要发到聊天或仓库。')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('授权导出未完成，原授权未修改；请核对输入、目标目录和密钥。')
        raise SystemExit(1) from None
