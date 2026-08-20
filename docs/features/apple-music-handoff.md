# Apple Music 自动交接

MusicFlow 会在转换、元数据和封面写入完成后，将成品复制到 Apple Music 的自动导入目录。Apple Music 负责后续的本地资料库整理，以及同步资料库的上传或匹配。

## 目录配置

以 AAC 输出为例：

```text
/mnt/d/Music/output/M4A/AAC/
├─ Converted\                         # MusicFlow 输出目录
├─ Automatically Add to Apple Music\  # Apple Music 自动导入目录
└─ Music\                             # Apple Music 管理的资料库目录
```

监控目录的输出目录应设置为 `/mnt/d/Music/output/M4A/AAC/Converted`。转换配置中开启“Apple Music 交接”，并填写 `/mnt/d/Music/output/M4A/AAC/Automatically Add to Apple Music` 的完整路径。

不要将 MusicFlow 输出目录设置为自动导入目录，也不要将 `Music` 目录配置为监控目录。Apple Music 会移走并整理交接文件；如果输出目录没有保留成品，后续扫描可能重复转换。

新增或重新启用自动处理的监控目录时，MusicFlow 会立即扫描已有音频；若对应预期输出文件已存在，则不会重复创建转换任务。

## 任务状态

| 状态 | 含义 |
| --- | --- |
| 等待接收 | 完整文件已复制到自动导入目录，等待 Apple Music 处理。 |
| 已接收 | 文件已从自动导入目录消失，通常表示 Apple Music 已取走该文件。 |
| 交接失败 | 自动导入目录未配置、无法写入，或存在同名但大小不同的文件。 |

“已接收”只表示 Apple Music 已从交接目录取走文件，不表示 Apple 云端同步一定完成。MusicFlow 不监控 `Music` 目录，也不读取 Apple Music 云端上传状态。
