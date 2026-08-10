# MusicFlow 启动/重启脚本

## 📁 脚本文件

| 脚本 | 功能 | 说明 |
|------|------|------|
| **start.bat** | 启动项目 | 启动后端和前端服务 |
| **stop.bat** | 停止项目 | 停止所有服务 |
| **restart.bat** | 重启项目 | 停止后重新启动 |
| **manage.bat** | 综合管理 | 菜单式管理工具 |

---

## 🚀 快速启动

### 方式 1：直接双击脚本

1. 打开文件夹 `D:\Documents\AI\MusicFlow`
2. 双击 `start.bat`
3. 等待服务启动完成
4. 打开浏览器访问 http://localhost:3000

### 方式 2：使用综合管理工具

1. 双击 `manage.bat`
2. 选择操作（1-6）
3. 按提示操作

---

## 📋 脚本功能

### 1. 启动项目 (start.bat)

**功能：**
- 停止现有服务
- 启动后端服务（端口 8082）
- 启动前端服务（端口 3000）

**使用：**
```bash
# 双击运行
start.bat

# 或在命令行运行
D:\Documents\AI\MusicFlow\start.bat
```

**输出：**
```
MusicFlow 已启动！

访问地址：
  前端：http://localhost:3000
  后端：http://localhost:8082
  API 文档：http://localhost:8082/docs
```

---

### 2. 停止项目 (stop.bat)

**功能：**
- 停止所有 Python 进程
- 停止所有 Node.js 进程

**使用：**
```bash
# 双击运行
stop.bat
```

**输出：**
```
所有服务已停止！
```

---

### 3. 重启项目 (restart.bat)

**功能：**
- 停止现有服务
- 重新启动所有服务

**使用：**
```bash
# 双击运行
restart.bat
```

**输出：**
```
MusicFlow 已重启！

访问地址：
  前端：http://localhost:3000
  后端：http://localhost:8082
  API 文档：http://localhost:8082/docs
```

---

### 4. 综合管理 (manage.bat)

**功能：**
- 菜单式操作
- 支持启动、停止、重启
- 查看服务状态
- 查看日志

**使用：**
```bash
# 双击运行
manage.bat
```

**菜单：**
```
1. 启动项目
2. 停止项目
3. 重启项目
4. 查看服务状态
5. 查看日志
6. 退出
```

---

## 🔧 常见问题

### 问题 1：脚本无法运行

**原因：** 权限不足或路径错误

**解决：**
1. 右键点击脚本文件
2. 选择 "以管理员身份运行"
3. 或者检查路径是否正确

### 问题 2：服务启动失败

**原因：** 端口被占用或依赖未安装

**解决：**
1. 运行 `stop.bat` 停止现有服务
2. 检查端口是否被占用：
   ```bash
   netstat -ano | find "8082"
   ```
3. 杀死占用端口的进程：
   ```bash
   taskkill /PID <进程ID> /F
   ```

### 问题 3：前端服务启动慢

**原因：** 首次启动需要安装依赖

**解决：**
1. 等待几分钟
2. 或者手动安装依赖：
   ```bash
   cd D:\Documents\AI\MusicFlow\frontend
   npm install
   ```

---

## 📊 服务状态检查

### 检查后端服务

```bash
# 测试后端 API
curl http://localhost:8082/health

# 应该返回
{"status":"healthy","version":"0.1.0",...}
```

### 检查前端服务

```bash
# 在浏览器打开
http://localhost:3000

# 应该看到 MusicFlow 界面
```

### 检查进程

```bash
# 查看 Python 进程
tasklist /FI "IMAGENAME eq python.exe"

# 查看 Node.js 进程
tasklist /FI "IMAGENAME eq node.exe"
```

---

## 🎯 使用场景

### 场景 1：每天开始工作

```bash
# 启动项目
双击 start.bat

# 或者使用管理工具
双击 manage.bat
# 选择 1
```

### 场景 2：结束工作

```bash
# 停止项目
双击 stop.bat

# 或者使用管理工具
双击 manage.bat
# 选择 2
```

### 场景 3：代码修改后重启

```bash
# 重启项目
双击 restart.bat

# 或者使用管理工具
双击 manage.bat
# 选择 3
```

### 场景 4：查看服务状态

```bash
# 使用管理工具
双击 manage.bat
# 选择 4
```

---

## 📝 脚本位置

所有脚本都在项目根目录：

```
D:\Documents\AI\MusicFlow\
├── start.bat         # 启动脚本
├── stop.bat          # 停止脚本
├── restart.bat       # 重启脚本
├── manage.bat        # 综合管理脚本
├── backend/
├── frontend/
└── ...
```

---

## ✅ 脚本特点

- ✅ 简单易用（双击即可运行）
- ✅ 自动停止现有服务
- ✅ 自动启动所有服务
- ✅ 显示访问地址
- ✅ 支持多种操作
- ✅ 菜单式管理工具
- ✅ 无需记忆命令

---

## 🚀 快速开始

**现在就可以使用：**

1. 打开文件夹 `D:\Documents\AI\MusicFlow`
2. 双击 `start.bat`
3. 等待 5-10 秒
4. 打开浏览器访问 http://localhost:3000
5. 开始使用 MusicFlow！

---

**祝你使用愉快！** 🎉
