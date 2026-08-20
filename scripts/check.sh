#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if ! command -v node >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh"
fi

if [ -x "$project_root/.venv/bin/python" ]; then
  python_cmd="$project_root/.venv/bin/python"
else
  python_cmd="python3"
fi

echo '[1/5] 后端测试'
"$python_cmd" -m pytest

echo '[2/5] Python 编译检查'
"$python_cmd" -m compileall -q backend/app backend/tests

echo '[3/5] 前端生产构建'
command -v node >/dev/null 2>&1 || { echo '未找到 Node.js。' >&2; exit 1; }
(cd frontend && npm run build)

echo '[4/5] Compose 配置检查'
command -v docker >/dev/null 2>&1 || { echo '未找到 Docker；请在 Docker Desktop 中启用 Ubuntu 的 WSL 集成。' >&2; exit 1; }
docker compose config -q

echo '[5/5] Git 空白字符检查'
git diff --check -- . ':(exclude)config/*.json' ':(exclude)logs/**'

echo '全部检查通过'
