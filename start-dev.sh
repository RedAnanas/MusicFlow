#!/bin/bash

# MusicFlow 开发服务器启动脚本

echo "=== 启动 MusicFlow 开发环境 ==="

# 安装依赖
echo "安装前端依赖..."
cd frontend
npm install

# 启动前端开发服务器
echo "启动前端开发服务器 (端口 3000)..."
npm run dev &
FRONTEND_PID=$!

# 等待前端服务器启动
sleep 3

echo ""
echo "=== 开发环境已启动 ==="
echo "前端: http://localhost:3000"
echo "后端: http://localhost:8082"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待用户中断
wait $FRONTEND_PID
