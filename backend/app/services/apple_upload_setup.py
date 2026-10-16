"""系统设置中的上传材料管理；不返回密钥和授权内容。"""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from app.config import settings

RUNTIME = Path(__file__).resolve().parents[3] / 'windows-upload'
if not RUNTIME.is_dir():
    RUNTIME = Path('/app/upload-runtime')
EXPECTED = {
    'AMPLibraryAgent.exe': 'ef493424c5768e8f5ffaf182463bee367ec68fffe1d886c06302a83ae7d427f3',
    'CoreFP.dll': '4cf0c86e5ba6b94c9a51fdbbec7104857fc5b7955fb09df663755362703f151e',
    'gnsdk_manager.dll': 'c51ce56f5afe11ebc1cc7e4d5ab747ace35f3990056f44bec767686ca13cfef6',
    'gnsdk_dsp.dll': 'b0fd7578afe2b2eb47e9b51dee89d79b78cb9a34fb3985c5a1f65b662316628f',
}


def binary_directory():
    return Path(os.environ.get('MUSICFLOW_APPLE_BINARY', str(Path(settings.DATA_DIR) / 'config/apple-upload/binaries/AMPLibraryAgent.exe'))).parent


def preparation_status():
    from app.services.apple_music_upload import apple_music_upload_service
    directory = binary_directory()
    files = []
    for name, digest in EXPECTED.items():
        path = directory / name
        valid = path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        files.append({'name': name, 'valid': valid})
    private = Path(os.environ.get('MUSICFLOW_UPLOAD_PRIVATE_DIR', str(Path(settings.DATA_DIR) / 'config/apple-upload/state')))
    key = os.environ.get('MUSICFLOW_UPLOAD_KEY_FILE')
    return {'supported': sys.platform == 'linux', 'files': files,
            'authorization_saved': (private / 'account.mfup').is_file(),
            'key_saved': bool(key and Path(key).is_file()),
            'worker': apple_music_upload_service.worker_status()}


def install_algorithms(files):
    if set(files) != set(EXPECTED):
        raise ValueError('请选择全部四个算法文件，文件名必须保持不变')
    for name, content in files.items():
        if hashlib.sha256(content).hexdigest() != EXPECTED[name]:
            raise ValueError(f'{name} 版本或校验值不匹配，未安装任何文件')
    directory = binary_directory()
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = directory / name
        if target.is_symlink():
            raise ValueError('算法目标不能为符号链接')
    for name, content in files.items():
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        try:
            temporary.replace(directory / name)
        finally:
            temporary.unlink(missing_ok=True)


def import_account(account, key=None):
    if sys.platform != 'linux':
        raise ValueError('加密授权需导入 Linux/Docker 服务端；当前平台仅提供准备工具下载')
    if not account.startswith(b'MFUP1\0') or (key is not None and len(key) != 32):
        raise ValueError('加密授权或密钥格式不正确')
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory)
        staging.chmod(0o700)
        source = staging / 'account.mfup'
        source.write_bytes(account)
        source.chmod(0o600)
        command = [sys.executable, str(RUNTIME / 'import-server-authorization.py'), '--input', str(source)]
        if key is not None:
            key_path = staging / 'store.key'
            key_path.write_bytes(key)
            key_path.chmod(0o600)
            command += ['--key-file', str(key_path)]
        try:
            result = subprocess.run(command, capture_output=True, timeout=40)
        except subprocess.TimeoutExpired:
            raise ValueError('授权导入超时，请等待当前上传结束后重试') from None
        if result.returncode:
            raise ValueError('导入失败，请检查密钥、账号一致性和执行器占用；原任务不会清空')


def desktop_tools():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        paths = [RUNTIME / name for name in ('worker.py', 'runtime.py', 'export-server-authorization.py', 'requirements-server.txt', 'start-authorization.cmd')]
        paths += list((RUNTIME / 'prototype').glob('*.py'))
        paths += [RUNTIME / 'prototype/requirements.txt', RUNTIME / 'scripts/authorize-client.py', RUNTIME / 'scripts/bootstrap-session.js', RUNTIME / 'scripts/prepare-authorization.ps1']
        for path in paths:
            archive.write(path, str(path.relative_to(RUNTIME)))
        archive.writestr('使用说明.txt', '仅用于 Windows 首次授权或重新授权。先安装 Python 3.12+（包含 Tcl/Tk）和 Apple Music 并登录。\n'
                          '完整解压后双击 start-authorization.cmd。首次自动创建工具专用 .venv，依赖缺失时征求同意后联网安装固定版本。\n'
                          '点击“读取并导出服务端授权”，选择首次授权或重新授权，再选择私密输出目录；成功后窗口显示导出位置。\n'
                          '将 state/account.mfup 和首次生成的 keys/store.key 导入系统设置。重新授权必须选择原 store.key。\n'
                          '取消或读取失败不会导出旧授权；每次使用新输出子目录，不覆盖已有导出。\n'
                          '算法文件来自已安装的 Apple Music 1.1540.23041.0 x64，选择系统设置列出的四个文件导入。\n'
                          '妥善保管密钥，不要发送到聊天或仓库；只通过可信连接传输。工具不会上传歌曲。')
    return output.getvalue()
