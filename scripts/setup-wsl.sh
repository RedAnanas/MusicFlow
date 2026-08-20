#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if ! command -v node >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh"
fi

command -v python3.12 >/dev/null 2>&1 || {
  echo '未找到 Python 3.12。请先安装 Python 3.12，再重新运行此脚本。' >&2
  exit 1
}
command -v node >/dev/null 2>&1 || { echo '未找到 Node.js；请先通过 NVM 安装 Node.js。' >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo '未找到 npm。' >&2; exit 1; }

if [ -d .venv ]; then
  if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    echo '检测到不完整的 .venv，请先将其移走或删除后重新运行初始化。' >&2
    exit 1
  fi
  venv_version="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [ "$venv_version" != '3.12' ]; then
    echo "现有 .venv 使用 Python $venv_version；请先将其移走或删除，再使用 Python 3.12 重新初始化。" >&2
    exit 1
  fi
else
  python3.12 -m venv .venv || {
    echo '无法创建 Python 3.12 虚拟环境。请确认已安装 python3.12-venv。' >&2
    exit 1
  }
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt
(cd frontend && npm ci)

echo 'WSL 开发依赖已准备完成。可使用 ./scripts/musicflow.sh start 启动项目。'
