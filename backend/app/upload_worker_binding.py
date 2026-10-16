"""在后端本地生成单个工作进程绑定，密钥只写指定文件，不输出到终端。"""

import argparse
import json
import os
import csv
import subprocess
from pathlib import Path
from app.services.apple_music_upload import apple_music_upload_service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Windows 可访问的 MusicFlow 地址")
    parser.add_argument("--output", type=Path, required=True, help="临时私密文件，导入 Windows 后删除")
    args = parser.parse_args()
    # 先独占创建文件，避免覆盖旧凭据后才发现绑定已存在。
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as output:
        if os.name == "nt":
            result = subprocess.run(["whoami.exe", "/user", "/fo", "csv", "/nh"], capture_output=True, check=True)
            sid = next(csv.reader(result.stdout.decode(errors="replace").strip().splitlines()))[1]
            subprocess.run(["icacls.exe", str(args.output), "/inheritance:r", "/grant:r", f"*{sid}:F", "*S-1-5-18:F"], capture_output=True, check=True)

        def save(binding):
            json.dump({"url": args.url.rstrip("/"), **binding}, output)
            output.flush()
            os.fsync(output.fileno())

        apple_music_upload_service.bind_worker(save)
    print("绑定已写入指定文件；请通过可信方式导入 Windows，随后删除该临时文件。")


if __name__ == "__main__":
    main()
