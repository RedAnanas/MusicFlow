"""MusicFlow 发布前兼容性检查入口。"""

import json
import sys

from app.config import settings
from app.services.preflight_service import PreflightService


def main() -> int:
    report = PreflightService(settings.CONFIG_DIR).check()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
