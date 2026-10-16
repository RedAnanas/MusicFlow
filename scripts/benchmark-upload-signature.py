"""离线比较旧指令计数与当前实现，不读取授权或发起上传。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcm', type=Path, required=True, help='16 kHz 单声道 float32 PCM，建议截取 10 秒')
    parser.add_argument('--runtime', type=Path, default=Path(__file__).resolve().parents[1] / 'windows-upload')
    parser.add_argument('--binary', type=Path, required=True, help='匹配版本的 AMPLibraryAgent.exe')
    args = parser.parse_args()
    os.environ['MUSICFLOW_APPLE_BINARY'] = str(args.binary)
    sys.path.insert(0, str(args.runtime))
    from prototype.audio_signature import generate_signature
    from prototype.windows_sap import Uc

    pcm = args.pcm.read_bytes()
    original = Uc.emu_start
    results = []
    try:
        for legacy in (True, False):
            def run(machine, begin, until, timeout=0, count=0):
                return original(machine, begin, until, timeout=timeout, count=200_000_000 if legacy else 0)
            Uc.emu_start = run
            started = time.perf_counter()
            signature = generate_signature(pcm)
            result = {'legacy_count': legacy, 'audio_seconds': len(pcm) / 64000,
                      'seconds': round(time.perf_counter() - started, 3),
                      'signature_sha256': hashlib.sha256(signature).hexdigest()}
            results.append(result)
            print(json.dumps(result), flush=True)
    finally:
        Uc.emu_start = original
    if results[0]['signature_sha256'] != results[1]['signature_sha256']:
        raise RuntimeError('优化前后签名不一致，禁止发布')


if __name__ == '__main__':
    main()
