# 服务端独立上传（实验）

日常上传在 MusicFlow 的 Linux/Docker 服务端运行。桌面客户端只用于首次登录和授权失效后的重新授权，不承担日常签名、指纹计算或资产上传。

## 已验证与限制

- Linux x86_64 已实测完成单曲上传，封面及歌词票据齐全，用户在另一设备确认可见且能播放。
- Linux 原生 FFmpeg 预处理、AES-GCM 授权与检查点保存、独立进程重新解密并查询服务均已验证。
- 支持单音轨 AAC LC M4A，以及 partial、full-lowres、Shazam signature 指纹；full-hires 尚未支持。
- 依赖固定版本 Apple Music Windows 1.1540.23041.0 的四个算法文件。它们在 Unicorn 来宾中执行，不启动 Windows 程序；不随公开镜像分发。
- 当前 macOS 授权导出工具尚未实现；首次授权使用已有 Windows 工具。
- Docker x86_64 已完成实际音频及附加资产上传，完整完成票据确认，用户已验证歌曲可播放。ARM 与 NAS 实机尚未验收。

## 运行结构

`转换并写入最终标签 → SQLite 上传队列 → 同容器执行器 → Apple 服务`

服务端自动建立内部队列身份，无需配对外部 Windows 工作进程。身份、账号和资料库必须匹配，重启复用原身份；不清空记录重新建歌曲。授权未就绪时等待；请求结果不明确时转人工核对，不自动重发。

后端任务及租约保存在 `DATA_DIR/musicflow.db`。协议检查点使用 AES-GCM 加密保存，密钥单独存放。兼容保留的部分检查点文件仍以 `.dpapi` 命名，但 Linux 内容是带 `MFUP1` 标识的 AES-GCM 密文，不是 Windows DPAPI。

## 首次桌面授权

在原 Windows 用户下，使用项目现有 `.venv`：

```powershell
.venv/Scripts/python.exe -m pip install -r windows-upload/prototype/requirements.txt -r windows-upload/requirements-server.txt
.venv/Scripts/python.exe windows-upload/scripts/authorize-client.py
```

在官方客户端完成登录、开启同步资料库，读取授权后退出客户端。使用私密目录导出：

```powershell
.venv/Scripts/python.exe windows-upload/export-server-authorization.py --output-directory '<私密导出目录>'
```

这会输出 `state/account.mfup` 和 `keys/store.key`。密钥不能发送到聊天、日志或仓库；通过可信传输交给服务器，传输副本由用户妥善移除。

## 容器准备与导入

先通过 MusicFlow 系统页准备原生 Linux FFmpeg/FFprobe。准备以下版本匹配的文件，放入持久卷的 `config/apple-upload/binaries`：

| 文件 | SHA-256 |
| --- | --- |
| AMPLibraryAgent.exe | ef493424c5768e8f5ffaf182463bee367ec68fffe1d886c06302a83ae7d427f3 |
| CoreFP.dll | 4cf0c86e5ba6b94c9a51fdbbec7104857fc5b7955fb09df663755362703f151e |
| gnsdk_manager.dll | c51ce56f5afe11ebc1cc7e4d5ab747ace35f3990056f44bec767686ca13cfef6 |
| gnsdk_dsp.dll | b0fd7578afe2b2eb47e9b51dee89d79b78cb9a34fb3985c5a1f65b662316628f |

文件必须来自用户合法安装的指定版本。仅复制这四个文件，不复制整份 Windows 程序目录或授权缓存。

将导出包临时放入容器可访问的传输目录，例如 `/data/upload-import`，然后在容器内导入：

```sh
docker compose exec musicflow python /app/upload-runtime/import-server-authorization.py --input /data/upload-import/state/account.mfup --key-file /data/upload-import/keys/store.key
docker compose restart musicflow
```

导入程序校验密文并以容器用户创建私密目录和文件，无需递归修改 NAS 权限。密钥及目录须仅容器运行用户可访问，且所有者与运行用户一致。默认位置：

- `/data/config/apple-upload/keys/store.key`：独立主密钥。
- `/data/config/apple-upload/state/account.mfup`：加密授权。
- `/data/config/apple-upload/state/`：加密检查点、内部身份与暂存媒体。

导入前请求执行器停止领取新任务，等待当前上传完成，不强制打断上传。若超过等待时间，按提示等当前任务结束再重试；失败不会清空原任务。导入成功后移走传输副本，并重启容器以恢复执行器。

备份需同时保留数据库、加密状态及独立密钥。不要生成新密钥覆盖旧密钥，否则已有授权和任务不可恢复。

## 使用与重新授权

在方案中选择“服务端独立上传（实验）”，使用 M4A/AAC 输出。授权和算法文件就绪后，转换完成会进入持久队列；界面展示执行器、授权和算法兼容状态。不会安装桌面开机任务，也不要求桌面电脑在线。

重新授权时，桌面导出使用 `--key-file '<原服务端密钥的安全副本>'` 和一个新的导出目录。服务端导入只提供 `--input`，复用原主密钥，完成后重启容器。账号或资料库身份发生变化时拒绝覆盖，需单独处理迁移。

已确认完成的歌曲不重新上传；未明确完成的网络请求不自动重发。此功能不包含云端删除、歌单同步或跨账号迁移。

## 本地验证

后端测试、上传器回归、Python 编译、前端生产构建及 Git 空白检查均应通过。实际 Compose 配置及容器测试需要 Docker CLI；缺少时必须记录未验证。

本地预览默认使用 `scripts/musicflow.ps1 start`。若 3000 端口被其他程序占用，可使用 `scripts/musicflow.ps1 start -FrontendPort 3001`；停止和状态检查使用相同端口参数。不得停止占用端口的其他程序。

真实上传及逆向证据见 [调查记录](../development/rea-linux-upload-investigation.md)，验证目标见 [Docker 验证门槛](../development/docker-upload-feasibility.md)。旧 Windows 工作进程入口仅为兼容保留，不是本方案的日常依赖。

### 系统设置入口

打开“系统设置 → Apple Music 服务端上传”，按顺序下载桌面授权工具、导入 `account.mfup`（首次同时导入 `store.key`）、选择并安装四个匹配版本的算法文件。下载包包含操作说明，不包含 Apple 二进制或真实授权。当前授权获取工具适用于 Windows；日常上传仍由 Linux/Docker 服务端执行。

材料导入会校验算法 SHA-256、授权加密格式及账号一致性，不清空原任务。重新授权沿用原密钥，导入时执行器等待当前上传完成，随后重新读取授权。导入失败后请按提示重试；等待期间不会强制中断当前上传。保存成功只表示加密材料已落盘，服务端授权有效性以执行器最近验证时间为准。方案编辑器只保留就绪提示与系统设置入口。

### 双击执行授权工具

从系统设置重新下载授权工具，完整解压后双击 `start-authorization.cmd`。电脑需预先安装 Python 3.12+（包含 Tcl/Tk）与 Apple Music。入口会检查 Python，在工具目录创建或复用 `.venv`，仅在固定版本依赖缺失时询问是否允许联网安装，不修改系统 Python。

窗口中点击“读取并导出服务端授权”，选择首次授权或重新授权。重新授权必须选择服务端原 `store.key`；随后选择私密输出目录。只有本次客户端授权读取成功后才导出，每次使用新的子目录，不覆盖已有导出。将导出的 `state/account.mfup` 和首次生成的 `keys/store.key` 导入系统设置。此工具不执行歌曲上传。

### 亚秒等待响应的兼容处理

Apple 工作响应可能返回 `retry-in-ms` 为 751、776 等小于 1000 的合法毫秒值。旧实现错误地拒绝这类值，导致握手和元数据成功后在工作处理阶段中止。当前接受 0–600000 的整数等待值，并至少等待 1 秒以避免忙轮询；负值、布尔值、非整数及超过上限的值仍拒绝。恢复时使用原工作会话和持久化票据，不重新提交歌曲元数据。

### 签名计算与缓存

工作响应要求至少三分钟空闲等待时，执行器在完整等待后重新查询原更新的工作路由，避免持续使用旧地址。刷新必须保持同一会话编号、曲目和工作序号；编号变化时停止并保留记录，不重新提交歌曲元数据。该处理不缩短 Apple 要求的退避时间。

首次生成签名仍逐段仿真整首音频。签名算法关闭逐指令计数，保留每次调用 30 秒超时、版本校验及返回点检查；旧版指纹仍使用原指令上限。任务列表显示签名百分比和本次计算耗时；百分比表示已处理的音频比例，不是上传总进度或剩余时间承诺。

签名按实际解码的 PCM 内容、算法版本和 PCM 转换规则缓存在私密状态目录的 `signature-cache/` 下。解码结果相同仅修改标签可以复用；重试或恢复时仍进行较快的解码校验，但跳过耗时仿真，避免相同 AAC 载荷带不同裁剪信息时误用签名。缓存带完整性校验，损坏后重新生成，失败不写入缓存。缓存不包含授权，也不会改变原任务的恢复和去重规则；保留原密钥与加密任务记录，不能用缓存替代备份。签名属于音频衍生数据，缓存不自动过期，可在停止上传后手动清理该目录。

离线测量使用 `scripts/benchmark-upload-signature.py --pcm <16k单声道float32文件> --binary <AMPLibraryAgent.exe>`。同一输入分别运行旧计数方式和当前实现，输出耗时及签名 SHA-256，并要求两次签名一致；不读取授权、不调用 Apple 接口。建议先用 FFmpeg 截取 10 秒，避免基准占用 NAS 过久。
