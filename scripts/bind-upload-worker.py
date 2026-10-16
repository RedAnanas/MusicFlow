"""从源码工作区运行工作进程绑定管理命令。"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.upload_worker_binding import main


if __name__ == "__main__":
    main()
