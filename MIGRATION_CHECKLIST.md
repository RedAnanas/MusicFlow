# MusicFlow 迁移清单（Mac）

## 快速迁移步骤

### 1️⃣ 在 Windows 上打包项目

```bash
# 使用 Git Bash 或 PowerShell
cd D:/Documents/AI

# 创建压缩包
tar -czvf MusicFlow.tar.gz MusicFlow/

# 或者使用 zip
# 右键 MusicFlow 文件夹 → 发送到 → 压缩文件夹
```

### 2️⃣ 传输到 Mac

**推荐方式（按优先级）：**

1. **USB 驱动器**（最快）
   - 复制 MusicFlow.tar.gz 到 USB
   - 插入 Mac
   - 复制到桌面

2. **AirDrop**（如果两台电脑都是 Apple）
   - 直接发送整个文件夹

3. **网络共享**
   - 启用 Windows 文件共享
   - 在 Mac 上通过网络访问

4. **云存储**
   - 上传到 Google Drive/Dropbox
   - 在 Mac 上下载

### 3️⃣ 在 Mac 上解压

```bash
cd ~/Desktop  # 或你想要的位置

# 解压
tar -xzvf MusicFlow.tar.gz

# 进入项目
cd MusicFlow
```

### 4️⃣ 运行快速设置脚本

```bash
# 给脚本执行权限
chmod +x setup-mac.sh

# 运行脚本
./setup-mac.sh
```

**脚本会自动：**
- ✓ 检查系统依赖
- ✓ 创建必要目录
- ✓ 配置环境变量
- ✓ 安装后端依赖
- ✓ 安装前端依赖
- ✓ 初始化 Git

### 5️⃣ 复制音乐文件

```bash
# 将你的音乐文件复制到源目录
cp -R /path/to/your/music/* ~/Music/source/
```

### 6️⃣ 启动项目

**启动后端（终端 1）：**
```bash
cd MusicFlow/backend
source venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8082 --reload
```

**启动前端（终端 2）：**
```bash
cd MusicFlow/frontend
npm run dev
```

### 7️⃣ 访问应用

- **前端界面：** http://localhost:3000
- **后端 API：** http://localhost:8082
- **API 文档：** http://localhost:8082/docs

---

## 保留的内容

✅ **已保留在项目中的所有内容：**

1. **Git 历史** - 完整的提交记录
2. **源代码** - 后端和前端所有代码
3. **文档** - README、架构、变更记录等
4. **配置** - Docker、环境变量、依赖
5. **规范** - AI 编程规范、Agent 规范
6. **测试文档** - 所有测试总结

---

## 验证迁移成功

### 检查 Git 历史
```bash
git log --oneline
# 应该看到 3 个提交
```

### 检查后端
```bash
curl http://localhost:8082/health
# 应该返回 JSON 响应
```

### 检查前端
```bash
# 在浏览器打开 http://localhost:3000
# 应该看到 MusicFlow 界面
```

---

## 常见问题

### ❌ FFmpeg 找不到
**解决：**
```bash
which ffmpeg  # 查找路径
# 更新 backend/.env 中的 FFMPEG_PATH
```

### ❌ Python 依赖失败
**解决：**
```bash
xcode-select --install  # 安装编译工具
pip install -r requirements.txt
```

### ❌ 端口被占用
**解决：**
```bash
lsof -i :8082  # 查找进程
kill -9 <PID>  # 杀死进程
# 或修改 backend/.env 中的 PORT
```

---

## 详细文档

📖 **完整迁移指南：** `MIGRATION_GUIDE.md`
- 详细的步骤说明
- 多种传输方式
- 完整的故障排除

---

## 迁移后的工作

### 继续开发
```bash
# 创建新分支
git checkout -b feature/<功能名称>

# 开发...
# 提交
git add <修改文件>
git commit -m "feat: <描述>"
```

### 多台电脑同步
```bash
# 推送到远程
git push origin master

# 在另一台电脑拉取
git pull origin master
```

---

## 传输方式对比

| 方式 | 速度 | 难度 | 推荐度 |
|------|------|------|--------|
| USB 驱动器 | ⭐⭐⭐⭐⭐ | 简单 | ⭐⭐⭐⭐⭐ |
| AirDrop | ⭐⭐⭐⭐ | 简单 | ⭐⭐⭐⭐ |
| 网络共享 | ⭐⭐⭐ | 中等 | ⭐⭐⭐ |
| 云存储 | ⭐⭐ | 简单 | ⭐⭐⭐ |
| SSH/SCP | ⭐⭐⭐⭐ | 复杂 | ⭐⭐ |

**推荐：** USB 驱动器或 AirDrop

---

## 迁移时间估算

- 打包项目：**5 分钟**
- 传输文件：**10-30 分钟**
- 解压项目：**5 分钟**
- 运行设置脚本：**5-10 分钟**
- 复制音乐文件：**5-10 分钟**
- 启动测试：**5 分钟**

**总计：** **35-65 分钟**

---

**迁移很简单！按照清单一步步操作即可！** 🎉
