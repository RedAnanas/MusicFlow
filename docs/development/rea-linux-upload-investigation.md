# REA：服务端上传内核调查记录

日期：2026-10-15。目标平台为 Linux/Docker x86_64；ARM 不是本轮验收要求。桌面端可用于首次授权和重新授权，日常上传必须在服务端独立执行。

## 分析环境

本轮通过 REA `binary_session` 实测确认 Ghidra 12.1.4 可用，使用独立 JDK 21.0.12.1。没有修改系统 Java，没有安装新软件。

分析对象为既有合法本地副本，不分发文件：

- `AMPLibraryAgent.exe`，SHA-256：`ef493424c5768e8f5ffaf182463bee367ec68fffe1d886c06302a83ae7d427f3`。
- `CoreFP.dll`，SHA-256：`4cf0c86e5ba6b94c9a51fdbbec7104857fc5b7955fb09df663755362703f151e`。

REA 已打开第一项，格式 PE、架构 x86_64，哈希与已有上传原型一致。以 `full-lowres` 定位指纹分支时，MCP 查询在 300 秒超时；改用 REA CLI 后 Ghidra 确实启动，但查询仍在 330 秒超时。当前没有取得该分支的字符串引用或反编译结果。MCP 目标会话已关闭。原生分析结果和受控仿真结果分开记录。

## 已完成的离线仿真验证

使用现有 Unicorn 原型执行 DLL 初始化和 SAP 上下文创建，不进行握手或网络请求，不读取账号、不调用官方客户端进程、不上传歌曲。

结果：`stage=sap_create`、`reason=returned`、`return_code=0`、`context_created=true`、`account_accessed=false`、`network_used=false`。此结果由本地探测脚本生成，不是 REA 静态分析证据。

对 Python 宿主接口解析进行观测，实际触达以下 Windows 接口；数量是接口查询次数，不是完整导入表，也不代表所有执行分支：

| 接口 | 查询次数 |
| --- | ---: |
| `GetACP` | 1 |
| `GetCPInfo` | 1 |
| `MultiByteToWideChar` | 6 |
| `GetStringTypeW` | 1 |
| `LCMapStringEx` | 4 |
| `WideCharToMultiByte` | 6 |
| `AreFileApisANSI` | 1 |
| `GetSystemInfo` | 1 |

进一步仅记录非敏感标量参数：

- 当前宿主 `GetACP` 返回 936；这不是其他机器的固定结果。
- 字符转换使用代码页 936 或 0（当前 ANSI 代码页），包含长度/容量查询。
- `GetStringTypeW` 使用类型 1，长度 256。
- 区域映射使用 `zh-CN`、标志 256/512，长度 256；本条路径未观察到排序键操作。
- 也存在长度 -1 的终止符字符串转换。

这说明当前实现确实受宿主代码页和区域语义影响。移植时不能直接把全部输入按 UTF-8 解释，也不能用 Python 的大小写处理无条件替换 Windows 映射。

## 尚待完成

1. 保留 Ghidra 对指纹分支的字符串、交叉引用和函数证据，确认输入输出及调用边界。
2. 实现并对照验证实际需要的 Linux 系统接口兼容层；未知代码页、标志或调用必须明确失败。
3. 在 Linux 实测 SAP 初始化、握手/签名和音频指纹；Windows 上的初始化成功不能代替这些检查。
4. 设计完整桌面授权包的加密导出与容器导入；不把 Windows DPAPI 密文直接交给 Linux。
5. 在用户指定歌曲后验证真实上传和服务端重启恢复，再接入生产上传执行器。

当前没有读取账号密文、发起 Apple 网络请求或改变云资料库。尚未验证 Linux 或 Docker 上传，也未验证 ARM。

## Linux 临时验证环境

经用户批准，在 WSL Ubuntu 的 /var/tmp 临时目录创建独立虚拟环境，仅安装 unicorn==2.1.4、pefile==2024.8.26。pip check、模块导入和版本断言均通过；跨 WSL 调用再次导入成功。平台为 x86_64，Python 3.14.4。最初 /tmp 中的环境在后续调用时已消失，因此改用 /var/tmp。

这只证明依赖可在当前 Linux 环境加载，不代表 SAP、指纹或 Docker 上传已通过。没有改系统 Python、Windows .venv 或 NAS，也没有读取授权或执行上传。


## Linux 离线运行结果

2026-10-15 使用临时探针做了两项跨平台对照，未修改生产上传执行器：

1. **SAP 初始化的严格宿主回放**：Windows 下记录 32 次匿名初始化宿主操作，包括模块/导出查询和接口的参数、输入及输出缓冲区；Linux 下逐项校验输入并回放输出，遇到额外或不同操作立即断言失败。Linux 实测 `stage=sap_create`、`return_code=0`、`context_created=true`，且 32 次操作全部消费。此路径证明 PE/Unicorn 执行可以跨平台，但仍使用 Windows 生成的固定记录，不是正式 Linux 兼容层。系统信息也是记录值，不能据此声称运行时硬件信息已移植。
2. **合成音频签名**：输入 16 kHz 单声道 float32、4 秒 440 Hz 合成音频。Windows 与 Linux 均输出 88 字节，SHA-256 均为 `f202ce4616eedf577057001b651d45386b9a66c3a5710970f4560cbb2e635320`。两侧宿主操作计数均为 0；Linux 使用空回放记录成功，说明这条路径不需要上述宿主 Windows 接口。此结果仅覆盖基础合成输入，不等于真实歌曲、partial 或 full-lowres 指纹验证。

探针包含目标二进制哈希校验、严格操作匹配、缓冲区长度及初始化返回值断言。过程文件保存在 Git 忽略的 temp 目录，不包含授权资料。后续仍需实现独立宿主兼容层、验证握手/签名和真实指纹分支，不能把回放探针作为上传执行器发布。

## 真实握手与用户指定歌曲验证

经用户明确授权发起握手、读取现有授权并尝试上传后：

- Windows 原型真实 SAP 握手成功，1 轮交换，测试签名 507 字节。
- WSL Linux x86_64 使用严格宿主回放再次执行真实 Apple 握手，同样 1 轮交换并生成 507 字节测试签名；握手网络响应未回放。宿主操作仍为 32 次。此结果仍不代表已完成独立系统接口兼容层，未比较签名字节一致性，也没有声称测试签名已被上传服务接受。
- 既有 DPAPI 授权包在 Windows 内存中解密，检查必要字段通过，没有导出授权明文至 Linux。
- 用户指定 M4A（AAC LC、44.1 kHz、双声道、289.55 秒）通过现有 Windows 上传入口创建单曲会话，服务端接受元数据并进入 hash-track、get-fingerprint。只提取受保护任务记录中的脱敏状态：8 次控制请求，服务端要求 fingerprint-type=partial，completed=false、audio_uploaded=false。

因此当前真实阻塞是 partial 指纹算法，不能宣称音频上传成功。既有受保护任务记录保留，不删除、不自动重建同一首歌曲；后续恢复必须沿用已确认的任务状态。云端可能已经出现待处理的元数据条目，不能把未发送音频理解为完全没有云端副作用。Docker 验收按用户要求暂缓。

## partial 指纹静态定位

复核同一 AMPLibraryAgent SHA-256 的既有 REA 证据：

- `pseudo-fingerprint-extraction.json`（ev_ec4bc4e49c4339190ee39ce3ee48a29484e92b57f9aa35e0d460302cdd383845）：类型 2 为 partial；get-fingerprint 将结果放入 fingerprint-value，而非按 Shazam 签名资产上传。
- `pseudo-legacy-fingerprint-create.json`（ev_eb8b2b4a5fbe21692e598cfe0d8fe4e20c8a155347ef3d26e00ffe79bbec87df）：类型 2/3/4 分别选择 Cantametrix-Q/NanoFAPI-Q/MicroFAPI-Q，类型 2 使用 16 位音频入口。
- 完成路径调用 DSP Ordinal 7、8 结束写入并取回文本，客户端以 strlen 长度复制；不能直接用原 Shazam 二进制替代。

本轮读取已安装客户端的 PE 导出表（普通静态检查，不当作 REA 证据）：DSP Ordinal 5/6/7/8/9 分别为 feature_audio_begin、feature_audio_write、feature_end_of_write、feature_retrieve_data、feature_release。DSP 另依赖 GNSDK_MANAGER.DLL；已有 SAP 仿真未载入这两项。

对 DSP 临时副本进行新的 REA/Ghidra 分析成功：SHA-256 b0fd7578afe2b2eb47e9b51dee89d79b78cb9a34fb3985c5a1f65b662316628f，入口 0x1800012e0，证据 ev_12317ed3e7019e0f3aa7b3aaa80e154e0c2280d651b8b8fe133a5c32df659d70。约 81 秒取得反编译，证实开始接口需要初始化状态和非空用户上下文，并对位宽 8/16/32 及通道参数做校验。原文件位于 WindowsApps，REA admission 拒绝直接读取该父目录，因此复制到 Git 忽略的 temp 并逐字节 SHA-256 核对；未修改安装文件或系统权限。

当前仅完成静态定位，尚未生成该歌曲的 partial 指纹，未恢复或重新创建云端任务。

DSP MCP 会话本轮又取得 7 条 REA 函数证据，已导出到 temp/gnsdk-dsp-evidence.json 并关闭会话。其中初始化证据 ev_2cf2945987274344d1cdab0ae8b27a6f125ec6a5d831f1a3fe68fa55b7302a71 明确要求匹配版本 3.06.1 的 manager handle；初始化内部通过 manager 查询句柄、错误及 SDK 许可接口。SDK 用户上下文与 Apple 上传授权是不同层，不能拿 Apple Cookie 替代，也不能伪造初始化成功。

- 0x180003490：DSP 内部初始化及 manager 接口注册。
- 0x180001220：算法名到内部类型的查表。
- 0x180001790：音频写入，验证上下文后更新完成标志。
- 0x180001df0：取回数据，结果未就绪时可返回 0x10a101a4；不能把此状态当成成功指纹。

后续工作需要继续还原客户端建立 GNSDK manager/user 的路径，再加载 DSP/manager 的实际算法；本轮不修改上传动作来填空值或伪报成功。

## GNSDK 上下文继续验证

本轮通过新的 REA manager 证据（ev_23b41821af4cbf964ee0e387fe2589aba9120e4b8ecf7c6b72fdae4514a5d408）确认，manager 初始化允许空许可输入建立基础句柄，但用户创建仍需独立的序列化用户资料与 SDK 校验；基础初始化成功不能等同用户上下文有效。

独立 Windows 原生探针在逐项核对 DLL 哈希后调用真实入口：manager_status=0、manager_created=true、dsp_status=0。未创建 SDK 用户或上传歌曲。

封闭 Unicorn 探针为 manager/DSP 分配不同映射基址、应用 PE 重定位并接通真实导出，依次运行两个 DLL 入口及 manager/DSP 初始化。新实现仅位于 Git 忽略的 temp，未知接口仍失败。增加了来宾堆块记录与扩容、TLS、信号量、模块查询、可逆指针编码等必要行为；来宾环境不继承宿主环境变量，不读取宿主默认密钥。最终 Windows 仿真到达 dsp_initialize，返回 0。

随后在 WSL Linux 使用 97 次严格匹配的宿主记录运行同一路径，亦到达 dsp_initialize 返回 0；网络握手及用户授权未参与本次 SDK 初始化。此结果仍是限定输入的回放实验，不是正式通用 Windows 兼容层。

用户歌曲已离线解码为 44.1 kHz、双声道、16 位 PCM，51070464 字节，仅保存临时副本，原 M4A 未修改。尚未生成 partial 结果或恢复云端上传。

## 实际歌曲 partial 结果与服务端恢复

本轮对同一首用户指定歌曲完成三侧对照：

- 真实 Windows DSP 内部算法调用：消费 2646000 字节 PCM（15 秒），产生 1 个结果块，最终文本 138 字节。
- Windows Unicorn 仿真：相同结果。
- WSL Linux Unicorn：相同结果，并通过与 Windows 原生结果逐字节相等断言。97 次初始化宿主操作严格匹配，音频算法没有增加宿主调用。

三者 SHA-256 均为 bc23a881893f38bcdbaffa9301df20e5648b35c4df0faf24bff47e339b35d88f。实际音频算法在 Linux 中运行，未回放指纹结果；初始化宿主接口仍用限定输入回放。算法探针从已定位的内部算法创建入口运行，不伪造 SDK 用户对象，也未改写 SDK 许可校验代码。结果不是官方客户端对该歌曲的现场采样，后续仍需服务端验证。

按原生 get-fingerprint 处理逻辑，以二进制 fingerprint-value、status=0 回显原 response-data，并使用既有 DPAPI 任务恢复上传，没有新增歌曲。第一次请求 HTTP 200、协议状态 4009、retry-in-ms=60000，不能据此推断指纹错误或会话过期。

查询原 update-id 得到状态 0、相同 session-id，但三类工作路由均与旧记录不同。使用刷新后的 upload-responses-url 重新提交已明确失败的同一工作结果后，收到协议状态 0、retry-in-ms=180000。服务端已接受这一协议步骤，尚未返回歌曲完成。诊断请求单独保存在 DPAPI 记录中；原歌曲记录保留完整请求轨迹及刷新后的工作路由。没有删除失败记录或重建单曲元数据。

等待探针按服务端 180 秒提示等待后再查询；原型原有 60 秒截断只在本轮临时探针中补足，尚未修改正式执行器。当前仍未执行 Linux 全流程上传或 Docker 验收。

恢复轮询时又发现上下文遗漏：原成功响应中存在 match-session 和 sequence-id=2，但 partial 结果回报响应只含状态和等待时间；原型 resume_work 只重放最后一条响应，导致后续 downloadRequests 不再携带这两个字段。当前仅在临时探针中从已保存的成功响应恢复缺失字段，保留服务端新响应中的字段优先级，并继续使用刷新路由。该遗漏是否导致此前长等待仍待实际后续任务确认，不能把静态发现直接当作云端原因。

进一步离线观测客户端 0x140260a88 容器构造入口：它直接调用 CFDataCreate，输入长度 138、输入 SHA-256 与上述 GNSDK 文本结果相同。未观察到额外 Base64 解码或私有头封装，当前以 plist 二进制字段回传原字节与这条路径一致。此为受控仿真观测，不是新 REA 静态证据。

补齐匹配上下文后，以及使用新路由重新同步原匹配任务后，服务端仍返回 status=0、retry-in-ms=180000、无 actions、无 all-work-completed。已停止重复轮询，保留原会话、刷新路由及受保护记录；没有删除云条目或创建重复歌曲。不能把工作结果请求 status=0 扩大为指纹匹配成功或整首上传完成。目前需要进一步定位旧会话的服务端匹配状态或等待任务恢复，不能伪造 complete。

## 官方请求对照的新发现

读取既有官方客户端受保护采样，仅输出动作名称、协议状态值、字段类型和指纹长度，不输出账号或其他歌曲元数据。官方 partial 回报的 fingerprint-value 为二进制，141 字节（旧采样音频，与当前歌曲不同），与本轮使用的字段类型一致。首次工作查询 match-state=12，哈希、partial/full-lowres/signature 准备与回报以及匹配查询使用 13，音频准备和上传使用 5；官方样本不携带本轮额外添加的 match-session。原型固定 12 是已观察到的差异，但单独改成 13 或去掉额外字段仍没有让旧会话产生后续任务，不能据此宣布根因已修复。

full-lowres 也已完成实际歌曲对照：Windows 原生、Windows Unicorn、WSL Linux Unicorn 三侧均输出 7250 字节，SHA-256 2496724fb158137589da6005973028e3841b4fd06308a2096dc54fd9b8d2259b。算法消费全曲 51070464 字节 PCM；Linux 宿主初始化仍为 97 次严格回放，算法结果由实际运行产生。为此修正临时 PE 加载探针：GNSDK manager 既有代码导出也有数据导出，IAT 必须指向真实代码或数据，不能将所有导出都当函数桩。原生和 Linux 结果逐字节断言通过。

准备沿用已有 cloud-id/persistent-id 建立新单曲更新会话时，发现 Apple Music 和 AMPLibraryAgent 正在运行，并发保护在发请求之前停止该实验，未提交新元数据。用户随后明确：正在查看这首歌，但客户端列表找不到该歌。因此不能把既有任务映射解释为歌曲已正式展示在资料库中。

Windows computer-use 两次激活目标窗口均返回 failed to activate captured window，未对错误窗口发送输入。已启动限定到源文件/音频摘要的被动 Frida 采样，等待用户在官方客户端导入该文件，以取得其真实工作流；仅选中歌曲的元数据/工作票据可进入 DPAPI 记录，其他歌曲数据不落盘。

用户已手动导入指定文件，并明确反馈：歌曲在列表中可见，云端状态为“已上传”。这证明官方客户端能够处理该文件，不代表独立上传器或 Docker 上传成功。首轮探针观察到选中歌曲元数据，但记录包含二进制字段，直接经 JSON 保存时出现 TypeError，因此没有获得可用于核对该歌曲完整上传流程的持久化记录。临时探针已改为二进制 plist 编码后再由 DPAPI 保护，并通过含二进制字段的往返断言；不要求用户删除或重新导入已上传歌曲。

## 匹配状态键与本地任务标志的进一步定位

只读附加同哈希 AMPLibraryAgent，读取协议键常量和已定位函数的机器指令，不调用业务函数、不发请求。确认 DAT_14118d870 是 match-state，而 DAT_14118d840 是 work-in-progress。因此 0x14079c814 检查的是本地任务队列是否仍有工作，并非 match-state 的位掩码计算；此前以此为候选匹配状态函数的推断已排除。

真正的 match-state 来自 0x1405f408c → 0x140780f18：在云资料库开启时读取对象偏移 0x1b8。进一步定位 0x14078b354 为状态设置函数，0x140604570 为状态名称映射。按后者的分支及静态字符串确认：5=Uploading、12=ImportingResults、13=LibraryMatching；12 不是通用工作状态。原型固定发送 12 是确定的行为差异，但旧会话改 13 后仍等待这一结果不变，尚无证据认定其为唯一根因。临时新会话探针已采用观察到的匹配 13 / 上传 5，但仍未发起新会话。

新增只读临时探针 temp/read-match-state.py，包含目标哈希、唯一进程、地址范围与键名断言；指令与键名记录不含授权或歌曲信息。没有删除、重新导入或再次上传已完成的歌曲。

REA 全程序分析完成后取得状态队列、状态设置器、名称映射及其调用者的证据，导出 temp/gnsdk-match-state-evidence.json（48 条记录）。关键证据：work-in-progress 判断 ev_4ac89ebb835fa0fad219d5d9e2d1fe28eed6371f979c3b439c9fe912c4b3e031；状态设置器 ev_9d3a90c403fb2da4b2ce2a87a4dc760031d74aab6c5c9a9885992aae1480c6b6；状态名称 ev_085bbe132ab4bd4eda64af913b0731fdf79e45e5c9558f1a813da6a4cd4cc4b7。

调用链 0x1408c47a8 / 0x1408cf230 → 0x1408cf564(event=0x17) → 0x140784020 → 0x14078b354(state=13) 表明：首次工作请求发出后即可从 12 切到 13，不要求响应含 hash-track。临时 retry-existing-song.py 已补齐首次 downloadRequests 成功返回后切到 13 的行为，后续上传态 5 不被查询覆盖；temp/check-existing-state.py 通过三个离线断言且未发网络请求。正式执行器尚未改动，旧会话没有重新查询，不能声称此时序修正已解决上传停滞。

只读请求信封对照另确认：官方工作查询带 sequence-id，动作结果回报不带，与原型一致；原型遗漏 library-name，但目前没有证据证明它导致停滞。尝试定位本机歌曲记录时确认 Library.musicdb 及 Genius.itdb 不可直接作为 SQLite 查询，已停止该路径，无资料库写入。

## 无 Windows 回放的 Linux 算法与真实服务请求

临时 portable-host.py 用 Python 标准库实现当前探针所需的字符转换、大小写映射、字符分类、系统信息及模块能力查询，不加载 Windows 系统 DLL，不读取宿主回放记录。明确使用 CP936 来宾环境；未验证的字符集合、其他 API 或参数仍停止，不把此探针当成通用 Windows 兼容层。原生接口记录仅供 check-portable-host.py 离线验证，Windows 和 Linux 均通过 34 个返回值及缓冲区逐字节对照。

在同一 WSL x86_64 临时 venv 中，当前实际结果为：

- 真实匿名 SAP 握手一轮成功，生成 507 字节签名；不再依赖先前 32 次宿主初始化回放。
- 实际歌曲 partial：138 字节，SHA-256 bc23a881893f38bcdbaffa9301df20e5648b35c4df0faf24bff47e339b35d88f，与 Windows 原生逐字节一致。
- 实际歌曲 full-lowres：7250 字节，SHA-256 2496724fb158137589da6005973028e3841b4fd06308a2096dc54fd9b8d2259b，与 Windows 原生逐字节一致。
- 4 秒 440 Hz 合成 PCM 的 Shazam 签名：88 字节，SHA-256 f202ce4616eedf577057001b651d45386b9a66c3a5710970f4560cbb2e635320，Windows 与 Linux 一致。

随后通过 Windows 侧解密既有 DPAPI 授权，经子进程标准输入仅传入 Linux 内存；Linux 自行握手、签名和发送旧会话状态查询，收到 HTTP 200、协议状态 0 和工作路由。授权未写 Linux 明文文件、命令行或日志。此为账号控制请求验证，不是歌曲上传成功。

工作查询收到 HTTP 200、协议状态 4009。将本次状态响应与旧任务对照，确认 session-id 和工作路由都已改变。此前官方客户端已处理上传，旧任务不能继续被当作当前会话使用。临时查询器已补上会话一致性判断：不一致时跳过工作查询；只读追加映射查询返回 4001，未获得可验证的新旧歌曲映射，不能推断云歌曲相同或不同。诊断响应仅在 Windows 由 DPAPI 保护，后续诊断采用新文件名保存，旧记录保留。

当前需用户指定另一首测试文件，或明确允许同一首歌新增受控测试条目，再进行 Linux 真上传；开始前需关闭官方客户端以免它再次切换会话。没有删除或重复上传现有成功歌曲。WSL 未发现原生 ffmpeg/ffprobe；真实 Docker 验收、独立加密授权包、正式执行器接入和重启恢复仍未完成，不能把本节验证称为 Docker 可用。

## 第二首歌曲：Linux 上传闭环已实测成功

用户另外指定“我们的歌 (Explicit) - DJ铁柱.m4a”，源文件 4669303 字节。开始前确认 AppleMusic / AMPLibraryAgent 均已退出。通过临时 linux-song-test.py 单独创建一次歌曲上传实验；按源文件摘要阻止重复创建，所有网络请求前后先经 Windows DPAPI 确认持久化，再允许 Linux 执行下一步。

完整过程由 Linux 负责 SAP 握手、最终请求体签名、控制请求、指纹生成和资产 PUT；未调用官方客户端 RPC。观察到流程为：创建单曲会话 → 元数据 → hash-track → partial → prepare-fingerprint(signature) → upload-fingerprint → prepare-track → upload-track → complete → 会话完成。共 15 次控制请求，最终 completed=true、audio_uploaded=true、complete_received=true；完成票据带有 artwork / lyrics token，extras_completed=true。该歌曲此次不需要 full-lowres 分支，不能把它计为本次服务端已接受的分支。

该曲 Linux partial 为 139 字节，SHA-256 236ab90c3233f7f94351e83f76efcce63f0fdd4e8c23c8dc379acc0e76daad60；独立 Windows 原生 DSP 对照结果相同。用户随后在另一台 Apple Music 设备确认“歌曲可见且能播放”。第一首歌曲未删除或重复上传。

验证边界：本次 Windows 仍负责调用已有 FFmpeg 生成 clean M4A、44.1 kHz PCM 和 16 kHz PCM，以及 DPAPI 检查点保存；Linux 没有直接调用 Windows 媒体程序，但实验启动及持久化仍有桌面依赖。此结果证明 Linux 上传协议和算法闭环，不等于日常 Docker 上传或掉电恢复已验收。

后续代码已开始收拢：portable_host.py 移入 prototype，windows_sap._open 在非 Windows 环境显式选择 HostAPI，不再依赖临时改写 ctypes 的全局状态。迁移后真实 Linux 握手再次成功；Windows 原有及新增宿主回归合计 68 项通过，Linux 4 项编码/容量/未知调用回归通过。

可移植 AES-GCM 会话存储和五项回归已准备，依赖固定为 cryptography==50.0.2；尚未安装或运行这组测试。已按用户此前的新增依赖确认约定，请求在现有 Windows .venv、已批准的 WSL 临时 venv 安装该依赖，并在 WSL 临时目录下载 Linux FFmpeg。收到确认后再执行，不修改系统 Python、NAS 或开机启动。正式服务端执行器、授权导入和恢复仍在进行，未提交、合并或发布。

## 2026-10-16 服务端接入与恢复验证

用户已批准在现有 Windows .venv 和 WSL 临时 venv 安装 cryptography==50.0.2，并在 WSL 临时目录下载原生 Linux FFmpeg。实际依赖安装及 pip check 通过；FFmpeg/FFprobe 从项目现有 BtbN 下载逻辑取得并校验 SHA-256，未修改系统 Python、NAS 或开机启动。

真实授权与第二首歌的完成记录经标准输入进入 Linux 内存，重封装为 AES-GCM 密文。密钥与状态分别位于已批准临时环境的 keys / state 私密目录，没有明文授权文件。新 Linux 进程自行读取密文、完成握手并向 Apple 查询，HTTP 200、协议状态 0，不调用 Windows 授权 RPC。原生 Linux FFmpeg 对该歌曲生成 clean M4A，mdat 音频字节不变，封面和歌词可提取。

生产协议模块已接入显式跨平台宿主接口及静态 GNSDK 加载器，运行时不再修改源码或全局 ctypes。partial、full-lowres 均经真实算法与原生结果对照；静态模块重新计算的 full-lowres 仍为 7250 字节并逐字节一致。工作循环补齐 12→13→5 状态、跨恢复的序号持久化，以及服务端三分钟等待不截断的问题。

容器内 server.py 复用现有 SQLite 队列、租约和事件协议，内部自动建立队列身份，不需要配对外部桌面。Linux 使用本地 FFmpeg、独立密钥和加密检查点；Dockerfile 只复制协议源码及执行器，不包含授权、密钥、官方算法文件或 Frida。缺少授权、算法或 FFmpeg 时仅等待，不创建上传请求。

已增加桌面加密导出、容器导入及授权更新暂停机制。新密钥、不同账号或损坏包不能覆盖原授权；等待当前上传结束后再更新，不强行终止正在执行的任务。恢复验证使用真实成功记录、新 Linux 执行器、Linux FFmpeg 和 AES 检查点，仅模拟后端回报，确认 cloud_completed 且未重新握手或重复发送 Apple 上传请求。

最终自动化检查：后端 140 项通过；上传器 87 项通过（Windows 跳过 5 项 Linux 专属测试）；Linux 47 项通过；Python 编译、前端生产构建、版本一致性、Git 空白检查通过。Compose YAML 语法与路径关系检查通过，但统一脚本因缺少 docker.exe 无法执行真正的 docker compose config；实际镜像构建、容器持久卷及 NAS 部署仍未验证。没有以 YAML 检查替代 Compose 验收。

本地前端默认 3000 被其他程序占用，未停止该程序。统一脚本增加 FrontendPort 参数，本次使用 3001 部署，后端 8082 和前端 3001 均 HTTP 200；方案编辑器显示“服务端独立上传（实验）”。仅还原本次启动产生、开始前无用户改动的 Vite 缓存。未改动用户的 issue-history.md，未提交、合并、升版或发布。


## 2026-10-16：Docker x86_64 上传与播放验收

在 WSL Ubuntu 的本地 Docker 容器完成加密授权导入、四个算法文件校验和实际歌曲上传。此次媒体准备、partial 与 Shazam signature 指纹、请求签名、音频和附加资产上传及检查点持久化全部在容器内执行。

首次工作响应返回 751/776 毫秒等待，被旧版最小 1000 毫秒校验误拒绝。新增回归后接受 0–600000 的整数，并至少等待 1 秒。沿原工作会话恢复后，`completed`、`audio_uploaded`、`complete_received`、`all_work_completed`、`extras_completed` 均确认，元数据仅提交一次。用户随后确认可播放；未重建歌曲或删除云条目。

本次验证不代表 ARM、NAS 实机、macOS 授权导出或全部歌曲指纹分支已通过。
