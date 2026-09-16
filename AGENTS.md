# AGENTS.md - MusicFlow 工程规范

## 项目信息

- 名称：MusicFlow - NAS 音乐转换工具
- 后端：Python 3.12+、FastAPI、Pydantic、Mutagen、FFmpeg、Watchdog
- 前端：Vue 3、TypeScript、Vite、Element Plus、Pinia、Vue Router
- 部署：Docker Compose

## 工作原则

1. 编码前明确假设、目标和验证标准；不确定时先说明。
2. 实现满足需求的最少代码，不做推测性扩展和无关重构。
3. 每一处改动必须能追溯到当前任务，并保持现有风格。
4. 缺陷修复应先复现或建立回归测试，再验证修复。
5. 回复、文档、代码注释、测试描述和 Git 提交使用简体中文；代码标识符使用英文。

## 分支与 Git

```text
main                 生产主干，禁止直接开发或提交
develop              日常集成分支
feature/<name>       新功能分支，从 develop 创建
fix/<name>           修复分支，从 develop 创建
```

标准流程：

1. 检查工作区并保护用户已有改动。
2. 从 `develop` 创建功能或修复分支。
3. 开发、测试并检查差异。
4. 完成一项或多项开发或修复后，自动重新部署本地项目并提供访问地址供用户手动验证。
5. 用户明确反馈验证通过后，提交并合并到 `develop`。
6. 只有用户明确确认后才能合并并推送 `main`。

提交格式：`<type>: <中文描述>`，其中 type 为 `feat`、`fix`、`docs`、`style`、`refactor`、`test`、`perf`、`build`、`ci` 或 `chore`。

禁止：

- `git reset --hard`
- `git push --force`
- 未经许可自动提交
- 未经明确确认合并到 `main`
- 提交 `.env`、密码、令牌、密钥、日志、任务历史、数据库备份或个人路径配置

## 项目结构

```text
backend/app/          后端源码
backend/tests/        后端测试
frontend/src/         前端源码
config/               本地运行配置，Git 忽略
config/examples/      脱敏配置示例
docs/                 当前文档与历史记录
scripts/              工程管理脚本
logs/                 本地日志，Git 忽略
temp/                 临时文件，Git 忽略
```

根目录仅保留项目入口、工程配置和核心目录。过程文档不得新增到根目录。

## 统一命令

```powershell
# 启动
.\scripts\musicflow.ps1 start

# 停止
.\scripts\musicflow.ps1 stop

# 重启
.\scripts\musicflow.ps1 restart

# 状态
.\scripts\musicflow.ps1 status

# 全量质量检查
.\scripts\check.ps1
```

访问地址：前端 `http://127.0.0.1:3000`，后端文档 `http://127.0.0.1:8082/docs`。

## 自动部署与手动验证

- 一项或多项开发或修复完成且质量检查通过后，必须主动重新部署本地项目，无需等待用户再次要求。
- 重新部署前检查端口、进程和运行中任务，避免误停其他进程或中断正在执行的转换；存在中断风险时先向用户说明并取得确认。
- 部署后检查前后端 HTTP 状态，向用户提供访问地址和本次变更的手动验证要点。
- 自动化检查和部署成功不能替代用户手动验证；只有用户明确反馈验证通过后，才能提交并合并到 `develop`。
- 合并或推送 `main` 仍需用户单独明确确认。

## 完成标准

任何代码改动交付前必须：

1. 相关测试通过；
2. Python 编译检查通过；
3. 前端生产构建通过；
4. Docker Compose 配置检查通过；
5. Git 空白错误检查通过；
6. 工作区差异只包含本次任务内容；
7. 文档、配置样例与实际行为一致。
8. 本地项目已重新部署，前后端状态正常，且已交由用户手动验证。

完整流程见 `docs/development/workflow.md`。
