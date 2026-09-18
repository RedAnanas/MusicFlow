# Apple Music 自动交接

MusicFlow 会在转换、元数据和封面写入完成后，将成品复制到 Apple Music 的自动导入目录。Apple Music 负责后续的本地资料库整理，以及同步资料库的上传或匹配。

## 目录配置

以 AAC 输出为例：

```text
D:\Music\output\M4A\AAC\
├─ Converted\                         # MusicFlow 输出目录
├─ Automatically Add to Apple Music\  # Apple Music 自动导入目录
└─ Music\                             # Apple Music 管理的资料库目录
```

监控目录的输出目录可设置为 `D:\Music\output\M4A\AAC\Converted`。转换配置中开启“Apple Music 交接”，并选择 Apple Music 的 `Automatically Add to Apple Music` 目录。

不要将 MusicFlow 输出目录设置为自动导入目录，也不要将 `Music` 目录配置为监控目录。Apple Music 会移走并整理交接文件；如果输出目录没有保留成品，后续扫描可能重复转换。

新增或重新启用自动处理的监控目录时，MusicFlow 会立即扫描已有音频；若对应预期输出文件已存在，则不会重复创建转换任务。

音乐文件页面的单个转换和批量转换也会复用同一任务链路。选择已开启 Apple Music 交接的转换配置后，任务完成时会自动将成品复制到自动导入目录。

单个和批量转换的输出目录可单独填写；留空时使用全局输出目录。转换配置不设置普通输出目录，只控制编码参数及 Apple Music 交接开关和自动导入目录。

## 任务状态

| 状态 | 含义 |
| --- | --- |
| 等待接收 | 完整文件已复制到自动导入目录，等待 Apple Music 处理。 |
| 已接收 | 文件已从自动导入目录消失，通常表示 Apple Music 已取走该文件。 |
| 交接失败 | 自动导入目录未配置、无法写入，或存在同名但大小不同的文件。 |

操作记录会单独显示 Apple Music 交接状态和错误原因。NAS 或 Windows 重启后，如果自动导入目录的挂载尚未恢复，交接会显示失败；挂载恢复后点击“重试交接”即可只重新复制已完成的成品，不会重新转换音频。

MusicFlow 会在自动导入目录保留 `.musicflow-apple-music-mounted` 隐藏标记，用于区分正常目录与挂载断开后出现的本地空目录。请勿删除该文件；如果标记不可访问，任务会显示“交接失败”，不会误报为“已接收”。

Docker 部署默认启用 SMB/CIFS 文件系统校验。挂载断开后，即使 NAS 上残留同名本地目录，MusicFlow 也会拒绝向该目录交接，并在操作记录中提示 SMB/CIFS 挂载不可用。Windows 本地运行不启用此限制。

已标记为“已接收”的记录也可选择“再次交接”，用于修复旧版本产生的误判；界面会先提示重复导入风险，请只对确认未被 Apple Music 接收的文件执行此操作。

“已接收”只表示 Apple Music 已从交接目录取走文件，不表示 Apple 云端同步一定完成。MusicFlow 不监控 `Music` 目录，也不读取 Apple Music 云端上传状态。
