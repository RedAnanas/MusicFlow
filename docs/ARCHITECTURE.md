# ARCHITECTURE.md - MusicFlow 系统架构

## 系统概述

MusicFlow 是一个基于 Docker 的 NAS 音乐转换与整理工具，采用前后端分离架构，支持自动监控、音频转换、元数据处理等功能。

---

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      用户界面层                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Vue 3 + Element Plus 前端                  │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │   │
│  │  │Dashboard│ │  Files  │ │  Tasks  │ │Profiles │   │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓ HTTP/REST                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              FastAPI 后端服务                        │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │   │
│  │  │  Files  │ │  Tasks  │ │Profiles │ │  Logs   │   │   │
│  │  │   API   │ │   API   │ │   API   │ │   API   │   │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   核心服务层                          │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │   │
│  │  │ Conversion  │ │   File      │ │  Metadata   │   │   │
│  │  │   Engine    │ │  Watcher    │ │   Service   │   │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   基础设施层                          │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │   │
│  │  │   FFmpeg    │ │   Mutagen   │ │  Watchdog   │   │   │
│  │  │   FFprobe   │ │             │ │             │   │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  数据存储层                          │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │   │
│  │  │   Config    │ │    Logs     │ │    Files    │   │   │
│  │  │   JSON      │ │   Files     │ │  Filesystem │   │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. 前端 (Vue 3 + Element Plus)

**职责：**
- 用户界面展示
- 用户交互处理
- API 调用
- 状态管理

**主要组件：**
- Dashboard：仪表盘页面
- Files：音乐文件管理
- Tasks：转换任务管理
- Profiles：转换配置管理
- WatchFolders：监控目录管理
- Logs：日志查看

**技术栈：**
- Vue 3 (Composition API)
- TypeScript
- Element Plus
- Pinia (状态管理)
- Vue Router
- Axios (HTTP 客户端)

---

### 2. 后端 (FastAPI)

**职责：**
- RESTful API 提供
- 业务逻辑处理
- 音频转换执行
- 元数据管理
- 文件监控

**主要模块：**

#### API 层 (app/api/routes/)
- files.py：文件管理 API
- tasks.py：任务管理 API
- profiles.py：配置管理 API
- watch_folders.py：监控目录 API
- settings.py：系统设置 API
- logs.py：日志查看 API

#### 核心服务 (app/core/)
- ffmpeg.py：FFmpeg 音频转换封装
- probe.py：FFprobe 音频信息读取
- metadata.py：Mutagen 元数据处理
- watcher.py：Watchdog 文件监控

#### 业务逻辑 (app/services/)
- conversion_engine.py：转换引擎
- task_manager.py：任务管理
- profile_manager.py：配置管理
- config_manager.py：配置文件管理
- logger_service.py：日志服务

#### 数据模型 (app/models/)
- Task：任务模型
- Profile：配置模型
- File：文件模型

---

### 3. 基础设施

#### FFmpeg/FFprobe
- 音频格式转换
- 音频信息读取
- 支持多种格式：FLAC、MP3、M4A、AAC、ALAC 等

#### Mutagen
- 元数据读取和写入
- 封面图片处理
- 支持多种格式的元数据

#### Watchdog
- 文件系统监控
- 文件创建/修改/删除事件
- 文件稳定性检测

---

## 数据流

### 1. 文件扫描流程

```
监控目录
    ↓
Watchdog 检测新文件
    ↓
文件稳定性检测（30秒）
    ↓
FFprobe 读取音频信息
    ↓
Mutagen 读取元数据
    ↓
保存到文件列表
    ↓
前端展示
```

### 2. 音频转换流程

```
用户选择文件
    ↓
选择转换 Profile
    ↓
创建转换任务
    ↓
提交到转换队列
    ↓
转换引擎处理
    ↓
FFmpeg 执行转换
    ↓
验证输出文件
    ↓
复制元数据
    ↓
更新任务状态
    ↓
前端显示结果
```

### 3. Profile 管理流程

```
用户创建/编辑 Profile
    ↓
前端验证
    ↓
调用后端 API
    ↓
后端验证
    ↓
保存到 JSON 文件
    ↓
返回结果
    ↓
前端更新列表
```

---

## 数据存储

### 配置文件 (JSON)

**位置：** /config/

**文件：**
- profiles.json：转换配置
- watch_folders.json：监控目录
- settings.json：系统设置

**特点：**
- 无需数据库
- 文件系统存储
- 自动备份
- 自动恢复

### 日志文件

**位置：** /logs/

**文件：**
- app.log：应用日志
- conversion.log：转换日志
- error.log：错误日志

**特点：**
- 日志轮转（10MB/文件）
- 保留 5 个备份
- 分级记录

### 音乐文件

**位置：**
- 源文件：/music/source
- 输出文件：/music/output
- 归档文件：/music/archive

**特点：**
- 不修改源文件
- 按 Profile 分目录
- 支持目录模板

---

## 并发控制

### 转换引擎

**配置：**
- 最大并发任务数：2（可配置）
- FFmpeg 线程数：2（可配置）
- 任务队列：异步队列

**实现：**
```python
class ConversionEngine:
    max_concurrent = 2
    current_concurrent = 0
    task_queue = asyncio.Queue()

    async def process_queue(self):
        while self.running:
            if self.current_concurrent < self.max_concurrent:
                task = await self.task_queue.get()
                self.current_concurrent += 1
                asyncio.create_task(self.execute(task))
```

---

## 错误处理

### 异常分类

1. **系统异常**：服务器错误、配置错误
2. **业务异常**：文件不存在、格式不支持
3. **转换异常**：FFmpeg 错误、验证失败

### 错误处理策略

1. **记录日志**：详细的错误信息
2. **返回错误**：清晰的错误响应
3. **任务状态**：更新任务为失败状态
4. **用户通知**：前端显示错误消息

---

## 安全性

### 文件访问控制

- 限制访问范围：/music、/config、/logs、/temp
- 路径安全检查：防止路径遍历
- 文件类型验证：只处理支持的音频格式

### 数据安全

- 不存储敏感信息
- 配置文件本地存储
- 日志脱敏处理

---

## 性能优化

### 1. 异步处理

- 异步任务队列
- 并发转换控制
- 非阻塞 I/O

### 2. 缓存策略

- 文件信息缓存
- 配置缓存
- 元数据缓存

### 3. 资源管理

- 线程池复用
- 连接池管理
- 内存优化

---

## 扩展性

### 水平扩展

- 多实例部署
- 负载均衡
- 分布式任务队列

### 垂直扩展

- 增加并发数
- 增加 FFmpeg 线程
- 优化算法

---

## 监控和日志

### 监控指标

- 任务执行数量
- 转换成功率
- 平均转换时间
- 系统资源使用

### 日志级别

- INFO：常规信息
- WARNING：警告信息
- ERROR：错误信息
- DEBUG：调试信息

---

## 部署架构

### Docker 部署

```yaml
services:
  musicflow:
    image: musicflow:latest
    ports:
      - "8080:8080"
    volumes:
      - ./config:/config
      - ./logs:/logs
      - /music/source:/music/source
      - /music/output:/music/output
```

### 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ RAM
- 2+ CPU 核心

---

## 未来规划

### 短期（1-3个月）

- [ ] 完善前端 UI
- [ ] 添加更多转换 Profile
- [ ] 优化转换性能
- [ ] 添加单元测试

### 中期（3-6个月）

- [ ] 添加 WebSocket 实时更新
- [ ] 支持远程 NAS 访问
- [ ] 添加用户认证
- [ ] 支持多用户

### 长期（6-12个月）

- [ ] 添加 MusicBrainz 集成
- [ ] 支持自动刮削
- [ ] 添加机器学习推荐
- [ ] 支持多语言

---

## 相关文档

- [README.md](../README.md) - 项目介绍
- [CHANGELOG.md](./CHANGELOG.md) - 变更记录
- [API 文档](http://localhost:8082/docs) - API 接口文档

---

**最后更新：** 2026-08-10
