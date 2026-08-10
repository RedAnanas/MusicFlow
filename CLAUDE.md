# CLAUDE.md - MusicFlow AI 编程规范

## 项目概述

MusicFlow 是一个基于 Docker 的 NAS 音乐转换与整理工具，支持：
- 自动监控音乐目录
- 多格式音频转换（FLAC、MP3、M4A、AAC、ALAC 等）
- 元数据和封面保留
- Web UI 管理界面
- 并发任务处理

## 技术栈

### 后端
- Python 3.12+
- FastAPI + Pydantic
- FFmpeg/FFprobe（音频转换）
- Mutagen（元数据处理）
- Watchdog（文件监控）
- JSON 配置存储

### 前端
- Vue 3 + TypeScript
- Element Plus UI
- Pinia 状态管理
- Vue Router
- Vite 构建工具

### 部署
- Docker + Docker Compose
- Nginx（前端静态文件）

---

## 开发环境启动

### 后端
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8082 --reload
```

### 前端
```bash
cd frontend
npm install
npm run dev
```

### 访问地址
- 前端：http://localhost:3000
- 后端：http://localhost:8082
- API 文档：http://localhost:8082/docs

---

## Git 规范

### 分支命名
```
feature/<功能名称>     # 新功能
fix/<问题名称>        # Bug 修复
refactor/<模块名称>   # 重构
docs/<内容>           # 文档修改
```

### Commit 格式
```
<type>: <description>

类型：feat | fix | docs | style | refactor | test | perf | build | ci | chore
```

### 示例
```
feat: add batch audio conversion support
fix: resolve file watcher duplicate event
refactor: simplify conversion engine
docs: update API documentation
```

---

## 代码规范

### Python
- 遵循 PEP 8
- 使用类型提示
- 使用中文注释和文档
- 异常处理完善
- 日志记录完整

### TypeScript/Vue
- 使用 Composition API
- 使用 TypeScript 类型
- 组件命名：PascalCase
- 变量命名：camelCase

---

## 项目结构

```
MusicFlow/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口
│   │   ├── config.py                # 配置管理
│   │   ├── api/routes/              # API 路由
│   │   ├── core/                    # 核心服务
│   │   ├── models/                  # 数据模型
│   │   ├── services/                # 业务逻辑
│   │   └── utils/                   # 工具函数
│   ├── requirements.txt
│   ├── Dockerfile
│   └── docker-compose.yml
├── frontend/
│   ├── src/
│   │   ├── views/                   # 页面组件
│   │   ├── stores/                  # Pinia 状态
│   │   ├── router/                  # 路由配置
│   │   └── types/                   # TypeScript 类型
│   ├── package.json
│   ├── Dockerfile
│   └── nginx.conf
├── docs/                            # 项目文档
├── CLAUDE.md                        # AI 编程规范
└── docker-compose.yml               # 项目级 compose
```

---

## 开发工作流

### 1. 开始任务
```bash
git status
git branch
git log --oneline -10
```

### 2. 创建分支
```bash
git checkout -b feature/<功能名称>
```

### 3. 修改代码
- 只修改任务相关文件
- 保持代码风格一致
- 添加必要的注释

### 4. 提交前检查
```bash
git diff
# 确认修改内容
```

### 5. 提交代码
```bash
git add <修改文件>
git commit -m "feat: <描述>"
```

### 6. 完成任务
输出：
- 修改内容
- 修改文件
- 测试情况
- Git 状态

---

## 禁止操作

- ❌ git reset --hard
- ❌ git push --force
- ❌ 删除远程分支
- ❌ 修改历史提交
- ❌ 自动提交代码（需用户确认）
- ❌ 修改无关代码
- ❌ 自动升级依赖

---

## 安全规则

禁止提交：
- .env 文件
- 密码、token、密钥
- 日志文件
- 数据库备份

---

## 测试要求

### 后端
- API 端点测试
- 转换引擎测试
- 元数据处理测试

### 前端
- 页面功能测试
- 组件渲染测试
- 状态管理测试

---

## 文档要求

所有修改必须更新：
- 代码注释（关键部分）
- API 文档（如有变更）
- CHANGELOG.md（重要变更）

---

## 工作完成标准

任务完成后必须输出：

```markdown
## Summary
修改内容：xxx

## Files Changed
- 文件1
- 文件2

## Tests
- 测试情况

## Git Status
- clean / modified

## Next Steps
- 后续建议
```
