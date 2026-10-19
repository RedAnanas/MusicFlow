"""单曲子进程入口；租约经标准输入传入，避免出现在命令行中。"""

import argparse
import json
from pathlib import Path
import sys

from runtime import PRIVATE, exclusive_lock
from prototype.local_session import load_session
from worker import Worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=int, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    job = json.load(sys.stdin)
    job_id = str(__import__("uuid").UUID(job["job_id"]))
    with exclusive_lock(f"{job_id}.lock"):
        worker = Worker(load_session(PRIVATE / "musicflow-binding.dpapi"), args.ffmpeg, args.target)
        worker.managed = True
        worker.parent_pid = args.parent
        worker.execute(job)


if __name__ == "__main__":
    main()
