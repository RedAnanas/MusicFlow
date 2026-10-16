# MusicFlow 独立上传执行器

使用方法、依赖安装计划和验证边界见 [独立上传说明](../docs/features/apple-music-direct-upload.md)。

协议模块、授权窗口、引导脚本和离线回归迁自用户于 2026-10-15 提供的 Windows 独立上传原型。首次迁入保持 `prototype` 结构；新增工作进程负责后端通信、租约、私密目录、互斥和恢复选择，不另写协议。

迁入适配：授权与上传共享本地锁，授权改存当前用户私密目录，官方二进制由参数指定，未支持指纹明确报错。不包含原型授权、票据、音频或 Apple 二进制。

运行不需要 REA 或 Ghidra。`server.py` 为 Linux/Docker 日常入口，复用现有队列协议，授权及检查点使用独立密钥加密；桌面只用于首次授权和重新授权。Windows 旧工作进程为兼容保留。

容器只复制协议源码和执行器，按 `requirements-server.txt` 安装 Unicorn、pefile、cryptography，不安装 Frida。授权、密钥、官方算法文件及实验数据不进入构建上下文。具体导入步骤及未验证边界见上述说明。
