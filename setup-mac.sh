#!/bin/bash
# MusicFlow 快速迁移脚本
# 在 Mac 上运行此脚本快速设置项目

echo "=================================="
echo "MusicFlow 快速迁移脚本"
echo "=================================="
echo ""

# 检查是否在项目目录
if [ ! -f "README.md" ]; then
    echo "❌ 错误：请在 MusicFlow 项目目录中运行此脚本"
    exit 1
fi

echo "✓ 检测到 MusicFlow 项目"
echo ""

# 步骤 1：检查并安装依赖
echo "步骤 1：检查并安装系统依赖"

# 检查 Homebrew
if ! command -v brew &> /dev/null; then
    echo "⚠ Homebrew 未安装，正在安装..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
echo "✓ Homebrew 已安装"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "⚠ Python 3 未安装，正在安装..."
    brew install python@3.12
fi
echo "✓ Python 3 已安装：$(python3 --version)"

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "⚠ Node.js 未安装，正在安装..."
    brew install node
fi
echo "✓ Node.js 已安装：$(node --version)"

# 检查 FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠ FFmpeg 未安装，正在安装..."
    brew install ffmpeg
fi
echo "✓ FFmpeg 已安装：$(ffmpeg -version | head -1)"

echo ""

# 步骤 2：创建目录
echo "步骤 2：创建必要目录"

mkdir -p config logs temp
echo "✓ 创建配置目录"

# 获取当前用户
CURRENT_USER=$(whoami)
HOME_DIR=$(eval echo ~$CURRENT_USER)

# 创建音乐目录
mkdir -p "$HOME_DIR/Music/source"
mkdir -p "$HOME_DIR/Music/output"
mkdir -p "$HOME_DIR/Music/archive"
echo "✓ 创建音乐目录"

echo ""

# 步骤 3：配置环境变量
echo "步骤 3：配置环境变量"

# 检测 FFmpeg 路径
if [ -f "/opt/homebrew/bin/ffmpeg" ]; then
    FFMPEG_PATH="/opt/homebrew/bin/ffmpeg"
    FFPROBE_PATH="/opt/homebrew/bin/ffprobe"
elif [ -f "/usr/local/bin/ffmpeg" ]; then
    FFMPEG_PATH="/usr/local/bin/ffmpeg"
    FFPROBE_PATH="/usr/local/bin/ffprobe"
else
    FFMPEG_PATH=$(which ffmpeg)
    FFPROBE_PATH=$(which ffprobe)
fi

cat > backend/.env << EOF
# MusicFlow 后端环境变量

# 服务器配置
HOST=0.0.0.0
PORT=8082
DEBUG=false

# 目录配置
MUSIC_SOURCE_DIR=$HOME_DIR/Music/source
MUSIC_OUTPUT_DIR=$HOME_DIR/Music/output
MUSIC_ARCHIVE_DIR=$HOME_DIR/Music/archive
CONFIG_DIR=$(pwd)/config
LOGS_DIR=$(pwd)/logs
TEMP_DIR=$(pwd)/temp

# FFmpeg 路径
FFMPEG_PATH=$FFMPEG_PATH
FFPROBE_PATH=$FFPROBE_PATH

# 任务配置
MAX_CONCURRENT_TASKS=2
FFMPEG_THREADS=2
FILE_STABLE_SECONDS=30
EOF

echo "✓ 创建 .env 配置文件"
echo "  FFmpeg: $FFMPEG_PATH"
echo ""

# 步骤 4：安装后端依赖
echo "步骤 4：安装后端依赖"

cd backend

# 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
    echo "✓ 虚拟环境已创建"
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "安装 Python 依赖..."
pip install -r requirements.txt -q
echo "✓ 后端依赖已安装"

cd ..

echo ""

# 步骤 5：安装前端依赖
echo "步骤 5：安装前端依赖"

cd frontend

# 安装依赖
echo "安装 Node.js 依赖..."
npm install
echo "✓ 前端依赖已安装"

cd ..

echo ""

# 步骤 6：初始化 Git（如果需要）
echo "步骤 6：检查 Git 配置"

if [ ! -d ".git" ]; then
    git init
    git config user.email "developer@musicflow.local"
    git config user.name "MusicFlow Developer"
    echo "✓ 初始化 Git 仓库"
else
    echo "✓ Git 仓库已存在"
fi

echo ""

# 步骤 7：验证安装
echo "步骤 7：验证安装"

# 测试后端
cd backend
source venv/bin/activate
python -c "import fastapi; import uvicorn; print('✓ 后端依赖正确')" 2>/dev/null || echo "⚠ 后端依赖验证失败"
cd ..

# 测试前端
cd frontend
node -e "require('vue'); require('element-plus'); console.log('✓ 前端依赖正确')" 2>/dev/null || echo "⚠ 前端依赖验证失败"
cd ..

echo ""

# 完成
echo "=================================="
echo "✓ 迁移完成！"
echo "=================================="
echo ""
echo "下一步："
echo ""
echo "1. 将你的音乐文件复制到："
echo "   $HOME_DIR/Music/source/"
echo ""
echo "2. 启动后端服务（终端 1）："
echo "   cd backend"
echo "   source venv/bin/activate"
echo "   python -m uvicorn app.main:app --host 127.0.0.1 --port 8082 --reload"
echo ""
echo "3. 启动前端服务（终端 2）："
echo "   cd frontend"
echo "   npm run dev"
echo ""
echo "4. 访问应用："
echo "   前端：http://localhost:3000"
echo "   后端：http://localhost:8082"
echo "   API 文档：http://localhost:8082/docs"
echo ""
echo "=================================="
