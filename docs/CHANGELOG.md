# CHANGELOG.md - MusicFlow 变更记录

本文件记录 MusicFlow 项目的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [未发布]

### 新增
- 完整的项目架构文档
- 项目工程规范文件（AGENTS.md）
- 详细的变更记录

---

## [0.1.0] - 2026-08-10

### 新增

#### 后端功能
- ✅ FastAPI 服务器框架
- ✅ 6 个 API 模块
  - Files API：文件管理
  - Tasks API：任务管理
  - Profiles API：配置管理
  - Watch Folders API：监控目录
  - Settings API：系统设置
  - Logs API：日志查看

- ✅ 核心服务
  - FFmpegService：音频转换封装
  - FFprobeService：音频信息读取
  - MetadataService：元数据处理（Mutagen）
  - ConversionEngine：转换引擎（异步、并发控制）
  - ConfigManager：配置文件管理
  - LoggerService：日志服务

- ✅ 转换功能
  - 支持 FLAC、MP3、M4A、AAC、ALAC 等格式
  - 多版本输出（一个文件可生成多个版本）
  - 元数据保留和转换
  - 封面图片处理
  - 转换验证

- ✅ 任务管理
  - 任务队列（异步处理）
  - 并发控制（可配置最大并发数）
  - 任务状态追踪
  - 进度更新
  - 任务取消和重试

- ✅ 配置管理
  - Profile CRUD 操作
  - 配置版本管理
  - JSON 文件持久化
  - 默认配置创建
  - 部分更新支持

- ✅ 文件监控
  - Watchdog 文件系统监控
  - 文件稳定性检测（30秒）
  - 自动发现新文件
  - 递归扫描

- ✅ 日志系统
  - 多日志文件（app.log、conversion.log、error.log）
  - 日志轮转（10MB/文件，保留5个备份）
  - 日志查询和统计
  - 分级记录（INFO、WARNING、ERROR、DEBUG）

- ✅ 健康检查
  - 服务状态检查
  - 转换引擎统计
  - 系统信息

#### 前端功能
- ✅ Vue 3 + TypeScript 框架
- ✅ Element Plus UI 组件库
- ✅ 6 个页面组件
  - Dashboard：仪表盘
  - Files：音乐文件管理
  - Tasks：转换任务管理
  - Profiles：转换配置管理
  - WatchFolders：监控目录管理
  - Logs：日志查看

- ✅ 状态管理（Pinia）
- ✅ 路由系统（Vue Router）
- ✅ API 代理配置
- ✅ 响应式布局
- ✅ 完整的类型定义

#### 配置和部署
- ✅ Docker 支持
  - 后端 Dockerfile
  - 前端 Dockerfile（多阶段构建）
  - Docker Compose 配置
  - Nginx 配置

- ✅ 环境变量配置
- ✅ 音乐目录映射
- ✅ FFmpeg 集成（Windows 版本）

### 修复

#### 后端修复
- ✅ 修复 Profile 更新的字段名转换问题
- ✅ 修复任务状态更新问题（转换完成后更新为 success）
- ✅ 修复进度回调机制
- ✅ 修复异常处理和错误信息

#### 前端修复
- ✅ 修复文件操作按钮（查看、转换、删除）
- ✅ 修复 Profile 编辑和更新功能
- ✅ 修复任务列表显示（字段名、状态、进度）
- ✅ 修复比特率选择（改为下拉框）
- ✅ 修复输出格式显示
- ✅ 移除版本字段

### 变更

#### 后端变更
- ✅ Profile 响应模型移除 version 字段
- ✅ 支持 Profile 部分更新（所有字段可选）
- ✅ 创建任务后自动触发转换引擎
- ✅ 转换引擎在后台启动任务队列处理

#### 前端变更
- ✅ 比特率从输入框改为下拉框选择
- ✅ 支持 8 个比特率选项（64-320 kbps）
- ✅ 改进的错误处理和用户反馈

### 测试

#### 已验证功能
- ✅ 文件扫描（13 个 FLAC 文件，447 MB）
- ✅ 元数据读取（蔡依林 - Pleasure 专辑）
- ✅ FFprobe 音频信息读取
- ✅ Profile 创建、更新、删除
- ✅ 任务创建和状态更新
- ✅ 转换引擎初始化
- ✅ 健康检查

---

## 版本说明

### 版本号规则

- **主版本号 (MAJOR)**：不兼容的 API 修改
- **次版本号 (MINOR)**：向下兼容的功能性新增
- **修订号 (PATCH)**：向下兼容的问题修正

### 示例

- 0.1.0：初始版本
- 0.2.0：新增功能
- 0.2.1：问题修复
- 1.0.0：正式发布

---

## 变更类型

### Added（新增）
- 新增功能

### Changed（变更）
- 已有功能的变更

### Deprecated（弃用）
- 即将移除的功能

### Removed（移除）
- 已移除的功能

### Fixed（修复）
- Bug 修复

### Security（安全）
- 安全相关的变更

---

## 日期格式

使用 ISO 8601 格式：YYYY-MM-DD

---

## 贡献指南

### 如何添加变更记录

1. 在 `[未发布]` 部分添加变更
2. 选择正确的变更类型（Added、Changed、Fixed 等）
3. 简洁描述变更内容
4. 发布时移动到对应版本号下

### 示例

```markdown
## [未发布]

### Added
- 新增批量转换功能

### Fixed
- 修复文件监控重复事件问题

---

## [0.2.0] - 2026-08-15

### Added
- 新增批量转换功能

### Fixed
- 修复文件监控重复事件问题
```

---

## 相关链接

- [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)
- [语义化版本](https://semver.org/lang/zh-CN/)
- [Conventional Commits](https://www.conventionalcommits.org/zh-hans/v1.0.0/)

---

**最后更新：** 2026-08-10
