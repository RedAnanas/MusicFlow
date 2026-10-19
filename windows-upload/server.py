"""同容器上传执行器；首次授权导入后串行领取 MusicFlow 队列。"""

import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime import PRIVATE, exclusive_lock
from worker import Worker, AUTHORIZATION_FILE
from prototype.local_session import load_session, save_session


def server_binding(service):
    """内部身份仅用于复用既有队列协议，不要求用户绑定外部电脑。"""
    path = PRIVATE / 'musicflow-binding.dpapi'
    if path.exists():
        binding = load_session(path)
        current = service.worker_status()
        if not current.get('bound') or any(current.get(key) != binding.get(key) for key in ('worker_id', 'account_scope')):
            raise RuntimeError('服务端上传身份与数据库不一致，请保留原记录')
        return binding
    binding = {}

    def persist(value):
        binding.update({'url': 'http://127.0.0.1:8082', **value})
        save_session(path, binding)

    service.bind_worker(persist)
    return binding


def main():
    if os.name == 'nt':
        raise RuntimeError('此入口仅用于 Linux 服务端')
    from app.services.apple_music_upload import apple_music_upload_service
    from app.services.system_service import system_service
    from prototype.windows_sap import EXPECTED, CORE_FP_HASH, SDK_IMAGES
    from worker import checksum

    waiting = False
    while True:
        try:
            if (PRIVATE / '.pause-for-authorization').exists():
                time.sleep(1)
                continue
            key = os.environ.get('MUSICFLOW_UPLOAD_KEY_FILE')
            target = Path(os.environ.get('MUSICFLOW_APPLE_BINARY', str(PRIVATE.parent / 'binaries/AMPLibraryAgent.exe')))
            ffmpeg, _ = system_service.find_binary('ffmpeg')
            expected = {'AMPLibraryAgent.exe': EXPECTED, 'CoreFP.dll': CORE_FP_HASH,
                        **{name: digest for name, (_, digest) in SDK_IMAGES.items()}}
            if (not key or not Path(key).is_file() or not (PRIVATE / AUTHORIZATION_FILE).is_file() or not ffmpeg
                    or not all(target.with_name(name).is_file() and checksum(target.with_name(name)) == digest for name, digest in expected.items())):
                raise RuntimeError('服务端上传材料尚未就绪')
            with exclusive_lock() as lock:
                bundle = load_session(PRIVATE / AUTHORIZATION_FILE)
                from worker import identity
                identity(bundle)
                binding = server_binding(apple_music_upload_service)
                from scheduler import UploadScheduler
                UploadScheduler(Worker(binding, Path(ffmpeg), target), lock).run()
            time.sleep(1)
        except KeyboardInterrupt:
            return
        except Exception:
            if not waiting:
                print('上传执行器等待授权、算法文件或 FFmpeg 就绪；尚未创建 Apple 上传请求。', flush=True)
                waiting = True
            time.sleep(10)


if __name__ == '__main__':
    main()
