# 🎵 MusicFlow

NAS 音乐转换与整理工具 - 自动监控、格式转换、元数据保留

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Vue](https://img.shields.io/badge/Vue-3.4-brightgreen.svg)](https://vuejs.org)
[![Docker](https://img.shields.io/badge/Docker-20.10+-blue.svg)](https://docker.com)

---

## ✨ 功能特性

- 🔄 **自动监控** - 监控音乐目录，自动发现新文件
- 🎵 **多格式转换** - 支持 FLAC、MP3、M4A、AAC、ALAC 等
- 📝 **元数据保留** - 保留标题、艺术家、专辑等元数据
- 🎨 **封面保留** - 保留嵌入式封面图片
- 📊 **多版本输出** - 一个文件可生成多个版本
- 🌐 **Web UI** - 完整的管理界面
- ⚡ **并发处理** - 支持多任务并行转换
- 🐳 **Docker 部署** - 单容器即可运行

---

## 🚀 快速开始

### 使用 Docker Compose（推荐）

```bash
# 克隆项目
git clone <repository-url>
cd MusicFlow

# 启动服务
docker compose up -d

# 访问
# 前端：http://localhost:8080
# 后端：http://localhost:8082
# API 文档：http://localhost:8082/docs
```

### 开发环境

#### 后端
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8082 --reload
```

#### 前端
```bash
cd frontend
npm install
npm run dev
```

---

## 📁 项目结构

```
MusicFlow/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置管理
│   │   ├── api/routes/          # API 路由
│   │   ├── core/                # 核心服务
│   │   ├── models/              # 数据模型
│   │   └── services/            # 业务逻辑
│   ├── requirements.txt
│   ├── Dockerfile
│   └── docker-compose.yml
├── frontend/
│   ├── src/
│   │   ├── views/               # 页面组件
│   │   ├── stores/              # Pinia 状态
│   │   ├── router/              # 路由配置
│   │   └── types/               # TypeScript 类型
│   ├── package.json
│   ├── Dockerfile
│   └── nginx.conf
├── docs/
│   ├── ARCHITECTURE.md          # 架构文档
│   └── CHANGELOG.md             # 变更记录
├── CLAUDE.md                    # AI 编程规范
├── AGENTS.md                    # Agent 规范
└── docker-compose.yml           # 项目级 compose
```

---

## 🔧 配置

### 环境变量

```bash
# 后端配置
MUSIC_SOURCE_DIR=/music/source      # 音乐源目录
MUSIC_OUTPUT_DIR=/music/output      # 输出目录
MAX_CONCURRENT_TASKS=2              # 最大并发任务
FFMPEG_THREADS=2                    # FFmpeg 线程数
```

### 音乐目录映射

在 `docker-compose.yml` 中配置：

```yaml
volumes:
  - /your/music/source:/music/source
  - /your/music/output:/music/output
```

---

## 📚 API 文档

启动后端后访问：
- **Swagger UI:** http://localhost:8082/docs
- **ReDoc:** http://localhost:8082/redoc

### 主要 API

- `GET /api/files/` - 获取音乐文件列表
- `POST /api/tasks/` - 创建转换任务
- `GET /api/tasks/` - 获取任务列表
- `GET /api/profiles/` - 获取转换配置
- `POST /api/profiles/` - 创建转换配置
- `GET /api/logs/` - 获取日志

---

## 🎯 使用流程

1. **配置监控目录** - 添加要监控的音乐目录
2. **创建转换配置** - 设置输出格式、比特率等
3. **启动监控** - 自动发现新音乐文件
4. **执行转换** - 手动或自动转换
5. **查看结果** - 在输出目录查看转换后的文件

---

## 🛠️ 技术栈

### 后端
- **框架:** FastAPI
- **音频处理:** FFmpeg, FFprobe, Mutagen
- **文件监控:** Watchdog
- **任务队列:** asyncio + ThreadPoolExecutor
- **数据存储:** JSON 文件

### 前端
- **框架:** Vue 3 + TypeScript
- **UI 组件:** Element Plus
- **状态管理:** Pinia
- **路由:** Vue Router
- **构建:** Vite

### 部署
- **容器:** Docker + Docker Compose
- **Web 服务器:** Nginx（前端）

---

## 📝 开发规范

请参考：
- [CLAUDE.md](./CLAUDE.md) - AI 编程规范
- [AGENTS.md](./AGENTS.md) - Agent 工作规范
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) - 系统架构

---

## 🤝 贡献

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交修改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📄 许可证

MIT License - 详见 [LICENSE](./LICENSE)

---

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Web 框架
- [Vue.js](https://vuejs.org/) - 渐进式 JavaScript 框架
- [Element Plus](https://element-plus.org/) - Vue 3 UI 组件库
- [FFmpeg](https://ffmpeg.org/) - 音视频处理工具
- [Mutagen](https://mutagen.readthedocs.io/) - 元数据处理库

---

## 📧 联系方式

- **Issues:** [GitHub Issues](<repository-url>/issues)
- **Email:** [your-email@example.com]

---

**⭐ 如果这个项目对你有帮助，请给个 Star 支持一下！**
