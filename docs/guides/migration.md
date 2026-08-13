# MusicFlow 项目迁移指南

## 迁移到 Mac 电脑

本指南帮助你将 MusicFlow 项目从 Windows 迁移到 Mac 电脑，并保留所有开发历史和配置。

---

## 迁移前准备

### 检查清单

- [ ] 确保所有代码已提交到 Git
- [ ] 确保所有文档已更新
- [ ] 备份当前项目
- [ ] 确认 Mac 电脑的系统版本

### 当前项目状态

- **Git 提交数：** 2 个提交
- **分支：** master
- **项目大小：** 约 50-100 MB
- **文件数量：** 12,379 个文件

---

## 方法 1：直接打包项目（推荐）

### 步骤 1：创建项目压缩包

在 Windows 上执行：

```bash
# 进入项目父目录
cd D:/Documents/AI

# 创建压缩包（保留所有文件和 .git）
# 使用 tar 命令（Git Bash 中可用）
tar -czvf MusicFlow-backup.tar.gz MusicFlow/

# 或使用 7-Zip（如果安装了）
# 右键 MusicFlow 文件夹 → 7-Zip → 添加到 "MusicFlow-backup.7z"

# 或使用 Windows 自带压缩
# 右键 MusicFlow 文件夹 → 发送到 → 压缩文件夹
```

### 步骤 2：传输到 Mac

**方法 A：使用 USB 驱动器**
1. 将压缩包复制到 USB 驱动器
2. 将 USB 插入 Mac
3. 复制压缩包到 Mac

**方法 B：使用网络传输**
1. 启用 Windows 文件共享
2. 在 Mac 上通过网络访问
3. 复制压缩包

**方法 C：使用云存储**
1. 上传压缩包到 Google Drive、Dropbox 等
2. 在 Mac 上下载

**方法 D：使用 SSH/SCP**
```bash
# 在 Windows 上（需要安装 OpenSSH）
scp MusicFlow-backup.tar.gz user@mac-ip:~/Desktop/
```

### 步骤 3：在 Mac 上解压

```bash
# 进入目标目录
cd ~/Desktop  # 或你想保存的位置

# 解压
tar -xzvf MusicFlow-backup.tar.gz

# 或者如果使用 zip
unzip MusicFlow-backup.zip

# 验证
ls -la MusicFlow/
```

---

## 方法 2：使用 Git 推送到远程仓库（推荐用于协作）

### 步骤 1：在 GitHub/GitLab 创建仓库

1. 登录 GitHub/GitLab
2. 创建新仓库：`MusicFlow`
3. 不要初始化 README、.gitignore 等（我们已经有了）
4. 复制仓库 URL

### 步骤 2：推送到远程

```bash
cd /path/to/MusicFlow

# 添加远程仓库
git remote add origin https://github.com/username/MusicFlow.git

# 推送
git push -u origin main
```

### 步骤 3：在 Mac 上克隆

```bash
cd ~/Desktop  # 或你想保存的位置

# 克隆仓库
git clone https://github.com/username/MusicFlow.git

# 进入项目
cd MusicFlow
```

**优点：**
- ✅ 保留完整的 Git 历史
- ✅ 可以在多台电脑间同步
- ✅ 便于协作
- ✅ 自动备份到云端

---

## Mac 环境配置

### 步骤 1：安装 Homebrew（如果没有）

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 步骤 2：安装 Python 3.12+

```bash
brew install python@3.12
```

### 步骤 3：安装 Node.js 18+

```bash
brew install node@18
```

### 步骤 4：安装 FFmpeg

```bash
brew install ffmpeg
```

### 步骤 5：验证安装

```bash
python3 --version  # 应该显示 Python 3.12.x
node --version     # 应该显示 v18.x.x
ffmpeg -version    # 应该显示 FFmpeg 版本
```

---

## 项目依赖安装

### 后端依赖

```bash
cd MusicFlow/backend

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # 激活虚拟环境

# 安装依赖
pip install -r requirements.txt
```

### 前端依赖

```bash
cd MusicFlow/frontend

# 安装依赖
npm install
```

---

## 配置调整

### 步骤 1：更新 .env 文件

编辑 `backend/.env`，修改路径为 Mac 格式：

```bash
# MusicFlow 后端环境变量

# 服务器配置
HOST=0.0.0.0
PORT=8082
DEBUG=false

# 目录配置（Mac 路径）
MUSIC_SOURCE_DIR=/Users/你的用户名/Music
MUSIC_OUTPUT_DIR=/Users/你的用户名/Music/output
MUSIC_ARCHIVE_DIR=/Users/你的用户名/Music/archive
CONFIG_DIR=/Users/你的用户名/Documents/AI/MusicFlow/config
LOGS_DIR=/Users/你的用户名/Documents/AI/MusicFlow/logs
TEMP_DIR=/Users/你的用户名/Documents/AI/MusicFlow/temp

# FFmpeg 路径（Mac 使用 Homebrew）
FFMPEG_PATH=/opt/homebrew/bin/ffmpeg
FFPROBE_PATH=/opt/homebrew/bin/ffprobe

# 任务配置
MAX_CONCURRENT_TASKS=2
FFMPEG_THREADS=2
FILE_STABLE_SECONDS=30
```

### 步骤 2：创建必要的目录

```bash
cd MusicFlow

# 创建目录
mkdir -p config logs temp
mkdir -p ~/Music/source ~/Music/output ~/Music/archive
```

### 步骤 3：复制音乐文件

```bash
# 将你的音乐文件复制到源目录
cp -R /path/to/your/music/* ~/Music/source/
```

---

## 启动项目

### 启动后端

```bash
cd MusicFlow/backend

# 激活虚拟环境（如果创建了）
source venv/bin/activate

# 启动服务器
python -m uvicorn app.main:app --host 127.0.0.1 --port 8082 --reload
```

### 启动前端（新终端）

```bash
cd MusicFlow/frontend

# 启动开发服务器
npm run dev
```

### 访问应用

- **前端：** http://localhost:3000
- **后端：** http://localhost:8082
- **API 文档：** http://localhost:8082/docs

---

## 验证迁移成功

### 检查清单

- [ ] Git 历史完整
  ```bash
  git log --oneline
  # 应该看到之前的提交
  ```

- [ ] 后端能启动
  ```bash
  curl http://localhost:8082/health
  # 应该返回 JSON 响应
  ```

- [ ] 前端能启动
  ```bash
  # 在浏览器打开 http://localhost:3000
  # 应该看到 MusicFlow 界面
  ```

- [ ] 能扫描音乐文件
  ```bash
  curl http://localhost:8082/api/files/
  # 应该返回音乐文件列表
  ```

- [ ] 能读取元数据
  ```bash
  curl http://localhost:8082/api/profiles/
  # 应该返回转换配置
  ```

---

## 常见问题

### 问题 1：FFmpeg 找不到

**原因：** FFmpeg 路径不正确

**解决：**
```bash
# 查找 FFmpeg 路径
which ffmpeg

# 更新 .env 中的路径
FFMPEG_PATH=<输出的路径>
```

### 问题 2：Python 依赖安装失败

**原因：** 缺少编译工具

**解决：**
```bash
# 安装 Xcode 命令行工具
xcode-select --install

# 然后重新安装依赖
pip install -r requirements.txt
```

### 问题 3：端口被占用

**原因：** 其他进程使用了相同的端口

**解决：**
```bash
# 查找占用端口的进程
lsof -i :8082

# 杀死进程
kill -9 <PID>

# 或修改 .env 中的端口
PORT=8083
```

### 问题 4：权限问题

**原因：** 目录权限不足

**解决：**
```bash
# 修改目录权限
chmod -R 755 ~/Music
chmod -R 755 MusicFlow/config
chmod -R 755 MusicFlow/logs
```

---

## 保留的记忆清单

### ✅ 已保留在项目中的内容

1. **Git 历史**
   - 所有提交记录
   - 分支信息
   - 完整的代码历史

2. **源代码**
   - 后端所有 Python 代码
   - 前端所有 Vue/TypeScript 代码
   - 所有配置文件

3. **文档**
   - README.md - 项目介绍
   - AGENTS.md - 工程与协作规范
   - AGENTS.md - Agent 工作规范
   - docs/ARCHITECTURE.md - 系统架构
   - docs/CHANGELOG.md - 变更记录
   - docs/TASKS.md - 任务管理
   - 所有测试总结文档

4. **配置**
   - Docker 配置
   - 环境变量配置
   - 依赖配置（requirements.txt、package.json）

5. **项目结构**
   - 完整的目录结构
   - 所有模块和组件
   - 所有服务和工具

---

## 迁移后的工作流

### 1. 继续开发

```bash
# 创建新分支
git checkout -b feature/<功能名称>

# 开发...
# 提交
git add <修改文件>
git commit -m "feat: <描述>"

# 推送
git push origin feature/<功能名称>
```

### 2. 同步多台电脑

```bash
# 在 Mac 上拉取最新代码
git pull origin master

# 在 Windows 上推送修改
git push origin master
```

### 3. 备份项目

```bash
# 定期推送到远程仓库
git push origin master

# 或创建备份
tar -czvf MusicFlow-backup-$(date +%Y%m%d).tar.gz MusicFlow/
```

---

## 回滚操作

### 如果迁移失败

```bash
# 删除迁移的项目
rm -rf ~/Desktop/MusicFlow

# 从备份恢复
cd ~/Desktop
tar -xzvf MusicFlow-backup.tar.gz

# 或重新克隆
git clone https://github.com/username/MusicFlow.git
```

---

## 性能优化建议

### Mac 特定优化

1. **使用 SSD**
   - 确保项目在 SSD 上
   - 提高文件读写速度

2. **增加内存**
   - FFmpeg 转换需要内存
   - 建议 8GB+ RAM

3. **使用 Homebrew**
   - 便于管理依赖
   - 自动处理依赖关系

4. **启用文件系统缓存**
   - 减少重复读取
   - 提高性能

---

## 迁移时间估算

- **打包项目：** 5-10 分钟
- **传输文件：** 10-30 分钟（取决于传输方式）
- **解压项目：** 5-10 分钟
- **安装依赖：** 10-20 分钟
- **配置调整：** 5-10 分钟
- **测试验证：** 10-15 分钟

**总计：** 45-95 分钟

---

## 迁移后检查

### 完整性检查

```bash
cd MusicFlow

# 检查 Git 状态
git status
git log --oneline

# 检查文件完整性
find . -name "*.py" | wc -l  # Python 文件数量
find . -name "*.vue" | wc -l  # Vue 文件数量
find . -name "*.ts" | wc -l   # TypeScript 文件数量

# 检查依赖
ls -la backend/requirements.txt
ls -la frontend/package.json
```

### 功能检查

```bash
# 启动后端
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8082

# 测试 API
curl http://localhost:8082/health
curl http://localhost:8082/api/profiles/
curl http://localhost:8082/api/files/
```

---

## 相关文档

- [README.md](../../README.md) - 项目介绍
- [AGENTS.md](../../AGENTS.md) - 工程与协作规范
- [ARCHITECTURE.md](../ARCHITECTURE.md) - 系统架构
- [CHANGELOG.md](../CHANGELOG.md) - 变更记录

---

**祝迁移顺利！** 🎉

---

**最后更新：** 2026-08-10
