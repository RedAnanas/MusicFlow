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
6. 仅在用户明确要求逆向时使用 REA；若 Codex 判断需要使用 REA 逆向，必须先说明目的与范围并取得用户明确确认，不得自行启动逆向。一般开发、排查或部署授权不包含 REA 逆向授权。

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

访问地址：前端默认 `http://127.0.0.1:3000`，后端文档 `http://127.0.0.1:8082/docs`。若 3000 被其他程序占用，先核实进程，不停止无关程序；可使用 `-FrontendPort 3001` 启动、停止、重启和检查对应实例。

## 环境与管理入口

| 环境 | 访问地址 | 管理入口与持久数据 |
| --- | --- | --- |
| NAS 正式环境 | `http://192.168.31.30:8080` | 容器及 Compose 项目 `musicflow`；配置 `/vol1/1000/Docker/musicflow/compose.yaml`；数据 `/vol1/1000/Docker/musicflow/data` |
| NAS 测试环境 | `http://192.168.31.30:18080` | 容器及 Compose 项目 `musicflow-test`；配置 `/vol1/1000/Docker/musicflow-test/compose.yaml`；数据 `/vol1/1000/Docker/musicflow-test/data`；专用下载目录 `/vol1/1000/Docker/musicflow-test/downloads` 挂载到 `/test-downloads` |
| 本机开发环境 | 前端默认 `http://127.0.0.1:3000`，冲突时可用 `http://127.0.0.1:3001`；后端 `http://127.0.0.1:8082` | Windows PowerShell 使用 `scripts/musicflow.ps1`；项目目录 `D:\Documents\AI\MusicFlow`；配置、日志、进程状态分别位于 `config/`、`logs/`、`temp/run/` |
| 本机 Docker 环境 | `http://127.0.0.1:18080` | WSL Ubuntu 中的容器及 Compose 项目 `musicflow-local`；配置 `config/docker-local/compose.yml`；数据 `/var/lib/musicflow-local/data`；Windows `D:\Music` 经 WSL `/mnt/d/Music` 挂载到 `/music` |

- 用户仅说“测试环境”时，默认指 NAS 测试环境；本机 Docker 环境必须明确称呼。目标不明确或指令与约定冲突时才询问，已经确认的部署范围不重复确认。
- Windows 开发服务使用 PowerShell 管理；WSL 用于本机 Docker，不沿用历史 WSL 开发服务启动方式。
- 本机开发与本机 Docker 使用独立配置、数据库和任务记录。不得为方便验证自动覆盖另一环境的数据、授权或密钥。
- NAS 正式环境使用 `musicflow_default`、`musicdl_default` 网络，测试环境使用 `musicdl_default`；更新前核实实际网络、挂载、端口和容器标识，保留既有配置。
- 表中地址与目录作为定位入口；版本、镜像标签、镜像 ID 和运行状态必须现场核查，不将历史快照当作当前事实。
- 本地 Docker 细节见 `docs/development/local-docker.md`，Windows 服务管理见 `docs/development/service-management.md`。

## NAS 技能与授权

- 所有 NAS 操作（包括读取、检查、文件传输、变更、部署及验证）必须加载并通过 `fnos` 技能（用户所称 fnskill）执行。技能入口为 `$CODEX_HOME/skills/fnos/SKILL.md`，以当前会话技能目录为准。
- 复用已授权 profile `nas-192.168.31.30`，对应 NAS `192.168.31.30`；沿用 profile 已保存的 HTTPS、端口与证书设置，不擅自修改 TLS 配置。
- 会话有效时直接使用，临期按技能流程刷新。只有确认授权失效、刷新失败或缺少当前操作所需 scope 时，才说明具体原因并请求重新授权；不能因为进入新会话或某次操作失败就重复要求 OAuth 登录。
- fnOS OAuth 授权与 SSH/sudo 权限分别处理。SSH 提示需要 sudo 密码，不代表 fnOS 授权失效。
- 技能能力不足时，明确说明具体缺口并等待用户决定；禁止自行改用 SSH/sudo、网页操作、直接 HTTP 请求或其他脚本绕过技能，也不猜测未文档化的写接口参数。用户要求“继续部署”不代表允许绕过本规则，只有用户明确修改本规则时才能变更操作方式。
- 密码、OAuth code、令牌、密钥和授权包内容不得进入聊天、AGENTS、日志或 Git。需要重新授权时遵循技能的交互流程，不要求用户将秘密发送到聊天。

## 自动部署与手动验证

- 一项或多项开发或修复完成且质量检查通过后，必须主动重新部署本地项目，无需等待用户再次要求。
- 重新部署前检查端口、进程和运行中任务，避免误停其他进程或中断正在执行的转换；存在中断风险时先向用户说明并取得确认。
- 部署后检查前后端 HTTP 状态，向用户提供访问地址和本次变更的手动验证要点。
- 自动化检查和部署成功不能替代用户手动验证；只有用户明确反馈验证通过后，才能提交并合并到 `develop`。
- 合并或推送 `main` 仍需用户单独明确确认。

## NAS 部署与环境隔离

- NAS 部署必须有明确的目标环境授权；正式部署需要单独明确确认。部署授权不自动授权 Git 提交、合并、推送或发布。
- 更新前检查目标环境的转换、上传、排队及授权或算法维护状态。核实活动进程，不能仅凭租约过期或页面无进度就判定任务已停止；有中断风险时先处理并取得确认。
- 切换前备份目标环境的 Compose、数据库及必要配置，记录旧镜像 ID、备份位置和回退条件。备份应保留一致性，包含授权或密钥时保持受限访问，不进入 Git。
- 仅更新指定 Compose 项目和服务，保留数据卷、账号绑定、既有任务、网络和挂载。禁止全局 `docker compose down`、清理卷或重启无关容器。
- 部署后核验实际容器镜像 ID、健康状态、前后端 HTTP、上传执行器及本次变更的关键接口。镜像构建、导入、Git 推送或 CI 成功均不能替代部署验证。
- 分别报告本地验证、NAS 测试验收和正式部署结果；说明哪些检查未运行，不把一处成功扩展为另一处已经部署或验收。
- NAS 正式与测试当前共用可写媒体挂载：宿主 `/vol2/1000/Media` 对应 `/Media`，宿主 `/vol02` 对应 `/Win_root`。独立数据目录不能隔离共享媒体写入；测试优先使用专用下载、输入和输出目录，不自动改为只读或调整权限。
- 同一 Apple Music 账号跨环境使用时，上传并发上限与成品去重记录按实例分别计算，不会跨环境共享。并行上传前须检查各环境活动任务、账号及资料库关系，并取得跨环境同时上传的确认，避免超出预期并发或重复提交。
- 数据库结构升级后，先确认旧版兼容性再决定回退方式。恢复数据库前核对部署后产生的新任务和上传证据，避免覆盖新记录或再次提交不确定请求。
- AGENTS 只记录环境职责、稳定入口和操作规则；临时镜像标签、部署结果、备份路径写入部署记录。含秘密或个人配置的具体内容保存在 Git 忽略的本地记录中。

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
