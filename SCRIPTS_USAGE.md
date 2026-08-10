# MusicFlow 脚本使用说明

## 问题说明

之前使用 `start` 命令会在新窗口中启动服务，但关闭主窗口后服务会停止。

**解决方案：** 使用 `start /B` 命令在后台启动服务，关闭窗口后服务继续运行。

---

## 脚本文件

| 脚本 | 功能 |
|------|------|
| **start.bat** | 启动项目（后台运行）|
| **stop.bat** | 停止项目 |
| **restart.bat** | 重启项目（后台运行）|
| **manage.bat** | 综合管理工具 |

---

## 使用方式

### 方式 1：启动项目（推荐）

```bash
# 双击运行
start.bat
```

**效果：**
- ✅ 服务在后台启动
- ✅ 可以安全关闭窗口
- ✅ 服务继续运行

### 方式 2：使用综合管理工具

```bash
# 双击运行
manage.bat

# 选择操作
1. Start Project
2. Stop Project
3. Restart Project
4. Exit
```

---

## 启动后的状态

### 正确的启动流程

```
1. 双击 start.bat
2. 看到 "MusicFlow Started!" 消息
3. 看到 "Services are running in background" 消息
4. 看到 "You can close this window safely" 消息
5. 按任意键关闭窗口
6. 服务继续在后台运行
```

### 访问应用

启动后，打开浏览器访问：

- **前端：** http://localhost:3000
- **后端：** http://localhost:8082
- **API 文档：** http://localhost:8082/docs

---

## 常见问题

### 问题 1：关闭窗口后服务停止

**原因：** 使用了普通的 `start` 命令

**解决：** 使用 `start /B` 命令（已在脚本中修复）

### 问题 2：端口被占用

**原因：** 之前的服务没有完全停止

**解决：**
```bash
# 先停止服务
双击 stop.bat

# 等待 2 秒

# 再启动服务
双击 start.bat
```

### 问题 3：服务启动失败

**检查：**
1. 确保已安装 Python 和 Node.js
2. 确保已安装依赖
3. 检查端口是否被占用

---

## 服务管理

### 查看服务状态

```bash
# 查看 Python 进程
tasklist /FI "IMAGENAME eq python.exe"

# 查看 Node.js 进程
tasklist /FI "IMAGENAME eq node.exe"

# 查看端口
netstat -ano | find "8082"
netstat -ano | find "3000"
```

### 停止服务

```bash
# 双击运行
stop.bat
```

### 重启服务

```bash
# 双击运行
restart.bat
```

---

## 最佳实践

### 1. 每天开始工作

```bash
# 双击 start.bat
# 等待启动完成
# 关闭窗口
# 打开浏览器访问 http://localhost:3000
```

### 2. 结束工作

```bash
# 双击 stop.bat
# 等待停止完成
# 关闭窗口
```

### 3. 代码修改后重启

```bash
# 双击 restart.bat
# 等待重启完成
# 关闭窗口
# 刷新浏览器页面
```

---

## 技术说明

### start /B 命令

```bash
# 在后台启动进程
start /B python -m uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
```

**特点：**
- ✅ 在后台运行
- ✅ 不会阻塞命令行
- ✅ 关闭窗口后继续运行
- ✅ 进程不会被终止

### 与普通 start 命令的区别

```bash
# 普通 start 命令（会在新窗口运行，关闭主窗口会停止）
start python -m uvicorn app.main:app

# start /B 命令（在后台运行，关闭窗口后继续运行）
start /B python -m uvicorn app.main:app
```

---

## 测试步骤

### 测试 1：启动项目

```bash
# 1. 双击 start.bat
# 2. 等待看到 "MusicFlow Started!" 消息
# 3. 按任意键关闭窗口
# 4. 打开浏览器访问 http://localhost:3000
# 5. 验证页面可以访问
```

### 测试 2：关闭窗口后验证

```bash
# 1. 启动项目（双击 start.bat）
# 2. 关闭所有终端窗口
# 3. 打开浏览器访问 http://localhost:3000
# 4. 验证页面仍然可以访问
```

### 测试 3：停止服务

```bash
# 1. 双击 stop.bat
# 2. 等待看到 "All services stopped!" 消息
# 3. 打开浏览器访问 http://localhost:3000
# 4. 验证页面无法访问
```

---

## 脚本位置

所有脚本都在项目根目录：

```
D:\Documents\AI\MusicFlow\
├── start.bat         # 启动脚本（后台运行）
├── stop.bat          # 停止脚本
├── restart.bat       # 重启脚本（后台运行）
├── manage.bat        # 综合管理脚本
├── backend/
├── frontend/
└── ...
```

---

## 总结

✅ **使用 `start /B` 命令在后台启动服务**
✅ **关闭窗口后服务继续运行**
✅ **安全可靠，不会意外停止**

---

**现在可以安全地使用脚本了！** 🎉
