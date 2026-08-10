------

# MusicFlow —— NAS 音乐转换与整理工具

## 1. 项目目标

开发一个基于 Docker 的 Web 音乐转换与整理工具，主要用于个人 NAS 环境。

用户将下载的音乐文件放入指定的输入目录后，程序自动：

```
监控目录
    ↓
发现新音乐
    ↓
读取音频信息和元数据
    ↓
根据规则决定是否转换
    ↓
执行 FFmpeg 转码
    ↓
保留/转换元数据
    ↓
保留/转换封面
    ↓
生成一个或多个目标版本
    ↓
校验输出文件
    ↓
保存到指定输出目录
    ↓
等待人工检查
```

同时提供完整 Web UI，让用户可以：

- 管理监控目录
- 管理输出目录
- 创建转换配置
- 设置编码器
- 设置比特率
- 设置采样率
- 设置声道
- 设置元数据处理方式
- 设置封面处理方式
- 设置文件命名规则
- 设置目录结构
- 创建多版本输出
- 手动选择文件转换
- 批量转换
- 查看音频信息
- 编辑元数据
- 重新转换
- 删除输出
- 查看日志
- 查看转换失败原因
- 手动重新处理

------

# 2. 核心设计原则

### 2.1 不使用数据库

本项目音乐数量不会非常大，不需要 PostgreSQL、MySQL、SQLite。

程序状态以：

```
文件系统
+
JSON 配置文件
+
日志文件
```

为主。

不要为了任务管理引入数据库。

------

# 3. Docker 部署

要求：

**单容器即可运行。**

容器内部包含：

```
MusicFlow
├── FastAPI
├── Vue3 前端
├── FFmpeg
├── FFprobe
├── Mutagen
├── Watchdog
└── Python Task Manager
```

不需要：

```
PostgreSQL
Redis
Celery
```

------

# 4. 推荐技术栈

## Backend

Python 3.12+

FastAPI

Pydantic

Uvicorn

Watchdog

Mutagen

asyncio / ThreadPoolExecutor

FFmpeg

FFprobe

------

## Frontend

Vue 3

TypeScript

Vite

Element Plus

Pinia

Vue Router

Axios

------

# 5. Docker目录结构

宿主机：

```
/volume1/docker/musicflow/
├── config/
├── logs/
└── temp/
```

音乐：

```
/volume1/music/
├── source/
├── output/
└── archive/
```

Docker：

```
services:
  musicflow:
    image: musicflow:latest
    container_name: musicflow
    restart: unless-stopped

    ports:
      - "8080:8080"

    environment:
      - TZ=Asia/Shanghai
      - PUID=1026
      - PGID=100

    volumes:
      - /volume1/docker/musicflow/config:/config
      - /volume1/docker/musicflow/logs:/logs
      - /volume1/docker/musicflow/temp:/temp

      - /volume1/music/source:/music/source
      - /volume1/music/output:/music/output
      - /volume1/music/archive:/music/archive
```

实际 UID/GID 不要写死，允许用户修改。

------

# 6. 配置文件

所有程序配置保存在：

```
/config/
```

例如：

```
/config/
├── settings.json
├── profiles.json
├── watch_folders.json
└── rules.json
```

配置修改后自动保存。

程序启动时自动加载。

配置损坏时不能导致程序启动失败，应：

1. 备份损坏配置
2. 创建默认配置
3. 写入日志
4. 启动程序

------

# 7. 首页 Dashboard

首页显示：

```
MusicFlow
────────────────────────

监控目录       3

待处理         12

转换中          2

已完成        1250

失败             3

今日转换        32

────────────────────────

当前任务
────────────────────────

周杰伦 - 七里香.flac
██████████████░░░░ 72%

AAC 256kbps
预计剩余 12 秒

────────────────────────
```

------

# 8. 监控目录

允许用户添加多个监控目录。

例如：

```
名称：
下载音乐

输入目录：
/music/source

输出配置：
Apple Music AAC

自动处理：
开启

递归扫描：
开启
```

------

## 支持多个监控目录

例如：

```
监控目录1
/download/music
→ Apple Music AAC


监控目录2
/download/lossless
→ Apple Lossless


监控目录3
/download/mp3
→ MP3 Archive
```

------

# 9. 支持的输入格式

至少：

```
MP3
FLAC
M4A
AAC
ALAC
WAV
APE
OGG
OPUS
WMA
```

程序通过 FFprobe 判断真实音频格式，而不是只根据扩展名判断。

------

# 10. 转换 Profile

这是整个项目最重要的功能之一。

用户可以创建多个转换 Profile。

例如：

```
Apple Music AAC 256
Apple Music Lossless
Mobile AAC
MP3 320
Archive ALAC
```

------

# 11. Profile 配置

每个 Profile 包含：

```
名称

启用状态

输入格式

输出格式

编码器

比特率

采样率

声道

质量模式

元数据策略

封面策略

歌词策略

文件名模板

目录模板

覆盖策略
```

------

# 12. 输出格式选择

支持：

```
M4A
MP3
FLAC
ALAC/M4A
WAV
OGG
OPUS
AAC
```

注意：

**输出格式和编码器必须动态联动。**

例如：

M4A 可以：

```
AAC
ALAC
```

MP3：

```
libmp3lame
```

FLAC：

```
flac
```

OPUS：

```
libopus
```

------

# 13. 比特率选择

AAC Profile：

```
64 kbps
96 kbps
128 kbps
160 kbps
192 kbps
224 kbps
256 kbps
320 kbps
自定义
```

MP3：

```
96
128
160
192
224
256
320
自定义
```

允许用户输入自定义值。

例如：

```
256k
```

------

# 14. 采样率选择

必须保留选择项。

提供：

```
自动 / 保持源文件

8000 Hz
11025 Hz
16000 Hz
22050 Hz
24000 Hz
32000 Hz
44100 Hz
48000 Hz
88200 Hz
96000 Hz
176400 Hz
192000 Hz
自定义
```

默认：

```
自动 / 保持源文件
```

------

# 15. 位深

对于支持的格式：

```
自动
16 bit
24 bit
32 bit
```

如果目标编码器不支持，则前端自动隐藏无效选项。

例如 AAC 不需要让用户设置 24bit。

------

# 16. 声道

提供：

```
自动 / 保持源文件

单声道

双声道

5.1

7.1

自定义
```

------

# 17. 编码质量模式

对于支持的编码器，允许：

```
Bitrate
CBR
VBR
Quality
```

例如 AAC：

```
CBR 256k
```

或者：

```
VBR Quality 5
```

不同编码器支持的参数必须动态变化。

------

# 18. 推荐预设

第一次使用时自动创建：

### Apple Music AAC 256

```
输出：
M4A

编码：
AAC-LC

Bitrate：
256kbps

Sample Rate：
44100Hz

Channels：
保持源文件

Metadata：
保留

Cover：
保留并嵌入
```

------

### Apple Lossless

```
输出：
M4A

编码：
ALAC

Sample Rate：
保持源文件

Metadata：
保留

Cover：
保留并嵌入
```

------

### MP3 320

```
输出：
MP3

Codec：
libmp3lame

Bitrate：
320kbps

Sample Rate：
44100Hz

Metadata：
保留

Cover：
保留
```

------

# 19. 多版本转换

这是必须实现的核心功能。

一个源文件可以同时生成多个版本。

例如：

```
输入：

周杰伦 - 七里香.flac
```

同时生成：

```
Apple Music AAC
↓
七里香.m4a


Apple Lossless
↓
七里香.m4a


MP3 320
↓
七里香.mp3
```

------

# 20. 多版本任务设计

用户创建：

```
输出方案：

☑ Apple Music AAC 256
☑ Apple Lossless
☐ MP3 320
☑ Mobile AAC
```

点击：

```
开始转换
```

程序生成：

```
任务组
 ├── AAC任务
 ├── ALAC任务
 └── Mobile AAC任务
```

任务之间互相独立。

某个失败不会影响其他版本。

------

# 21. 输出目录

每个 Profile 可以单独配置输出目录。

例如：

```
Apple Music AAC
→ /music/output/apple


Apple Lossless
→ /music/output/alac


MP3
→ /music/output/mp3
```

------

# 22. 目录模板

支持变量：

```
{artist}
{album_artist}
{album}
{title}
{year}
{genre}
{track}
{disc}
{composer}
{extension}
```

例如：

```
{album_artist}/{year} - {album}/{track} - {title}.{extension}
```

结果：

```
周杰伦/
└── 2004 - 七里香/
    ├── 01 - 我的地盘.m4a
    ├── 02 - 七里香.m4a
    └── 03 - 借口.m4a
```

------

# 23. 文件名安全处理

必须处理：

```
/
\
:
*
?
"
<
>
|
```

不能因为 Windows/Linux 文件名非法导致任务失败。

提供：

```
非法字符替换为：
-
```

或者：

```
删除
```

------

# 24. 元数据处理

使用：

**Mutagen**

读取：

```
Title
Artist
Album
Album Artist
Composer
Genre
Date
Year
Track
Disc
Comment
Copyright
Grouping
Lyrics
Cover
```

------

# 25. 元数据策略

Profile 中提供：

```
保留原始元数据
覆盖目标元数据
不写入元数据
转换后重新刮削
```

默认：

```
保留原始元数据
```

------

# 26. 元数据映射

不同格式必须正确映射。

例如：

FLAC：

```
TITLE
ARTIST
ALBUM
ALBUMARTIST
DATE
TRACKNUMBER
DISCNUMBER
GENRE
```

M4A：

```
©nam
©ART
©alb
aART
©day
trkn
disk
©gen
```

程序不得简单复制字符串，而要进行格式映射。

------

# 27. 封面处理

支持：

```
不处理

保留外部封面

嵌入封面

嵌入 + 保留外部封面
```

支持：

```
JPG
JPEG
PNG
```

默认：

```
嵌入封面
```

------

# 28. 多张封面

如果源文件存在：

```
Front
Back
Booklet
Artist
```

默认只取：

```
Front
```

如果没有 Front：

```
取第一张
```

------

# 29. 歌词

支持读取：

```
内嵌歌词
.lrc
.txt
```

提供：

```
不处理

保留内嵌歌词

嵌入目标文件

复制LRC
```

注意：

不同音频格式对歌词支持不同。

如果目标格式无法安全保存歌词，应给出提示，而不是静默丢失。

------

# 30. 转码前检查

开始转换前：

```
检查文件是否存在

检查文件是否可读取

检查FFprobe是否能解析

检查音频流是否存在

检查目标目录权限

检查磁盘空间
```

磁盘空间不足：

直接阻止任务启动。

------

# 31. 转码后验证

必须自动执行：

```
FFprobe重新读取输出文件
```

检查：

```
文件存在

文件大小 > 0

可以正常解码

Duration正常

Codec正确

Sample Rate正确

Channels正确

Bitrate符合预期

Metadata存在

Cover存在
```

验证失败：

```
任务 = FAILED
```

并保留临时文件用于排查。

------

# 32. 原始文件保护

默认：

**绝对不能修改源文件。**

流程：

```
source
 ↓
读取
 ↓
转换
 ↓
output
```

禁止：

```
转换成功后删除源文件
```

除非用户明确开启：

```
☑ 转换成功后删除源文件
```

而且必须二次确认。

------

# 33. 覆盖策略

输出文件已经存在时：

```
跳过

覆盖

自动重命名

询问
```

默认：

```
跳过
```

------

# 34. 自动监控

使用：

```
watchdog
```

支持：

```
创建
修改
移动
```

但不能文件一出现就立即转换。

例如下载程序正在写：

```
song.flac
```

可能还没下载完成。

因此必须增加：

## 文件稳定检测

例如：

```
文件大小连续30秒不变化
```

才认为下载完成。

这个功能非常重要。

------

# 35. 自动扫描

除了 Watchdog，还应该提供：

```
立即扫描
```

以及：

```
每5分钟扫描

每15分钟扫描

每30分钟扫描

每小时扫描

关闭
```

防止 Watchdog 漏事件。

------

# 36. 手动文件管理

文件列表显示：

```
文件名

格式

大小

时长

采样率

比特率

Artist

Album

状态
```

操作：

```
查看

编辑Metadata

转换

重新转换

刮削

移动

删除

打开所在目录
```

------

# 37. 批量操作

支持多选：

```
批量转换

批量编辑标签

批量刮削

批量重新转换

批量删除

批量移动
```

------

# 38. 元数据编辑器

类似简化版 Mp3tag。

支持：

```
单文件编辑
批量编辑
```

批量：

```
Artist → 周杰伦
Album Artist → 周杰伦
Genre → 华语流行
Year → 2004
```

保存后直接写回文件。

------

# 39. 音频信息查看

详细页面：

```
文件：

七里香.flac


格式：

FLAC


Codec：

FLAC


Duration：

04:59


Sample Rate：

96000Hz


Bit Depth：

24bit


Channels：

2


Bitrate：

2.8Mbps
```

Metadata：

```
Artist
Album
Title
Track
Disc
Year
Genre
```

------

# 40. 手动查验模式

增加一个非常重要的功能：

## “转换前预览”

用户选择歌曲后显示：

```
源文件

FLAC
96kHz
24bit
2.8Mbps
```

↓

目标：

```
M4A
AAC
256kbps
44.1kHz
2 channels
```

同时显示：

```
预计文件大小
预计处理时间
Metadata是否保留
Cover是否保留
```

然后：

```
[取消] [开始转换]
```

------

# 41. FFmpeg命令预览

高级用户可以看到：

```
ffmpeg -i "input.flac" \
-map 0:a \
-map 0:v? \
-c:a aac \
-b:a 256k \
-ar 44100 \
-movflags +faststart \
"output.m4a"
```

提供：

```
复制命令
```

但是：

**不要让用户直接编辑 FFmpeg 命令作为主要配置方式。**

应该由 UI 参数生成命令。

------

# 42. 任务中心

显示：

```
等待
转换中
成功
失败
取消
跳过
```

每个任务：

```
输入
输出
Profile
开始时间
结束时间
耗时
进度
错误信息
```

------

# 43. 并发控制

设置：

```
最大并发：

1
2
3
4
自定义
```

默认：

```
2
```

不要默认无限并发。

NAS CPU 和硬盘同时读取多个 FLAC 时，过高并发可能反而降低性能。

------

# 44. CPU资源控制

提供：

```
最大并发任务
FFmpeg线程数
```

不要强制使用所有 CPU。

------

# 45. 日志

日志目录：

```
/logs
```

例如：

```
app.log
conversion.log
error.log
```

Web 页面可以查看：

```
实时日志
```

支持：

```
INFO
WARNING
ERROR
DEBUG
```

------

# 46. 错误处理

FFmpeg失败：

不能只显示：

```
转换失败
```

必须显示：

```
FFmpeg exit code: 1

具体错误：
xxxx
```

并允许：

```
重新尝试

查看完整日志
```

------

# 47. 去重

第一阶段不要实现复杂的音频指纹。

只实现：

```
源文件路径
文件大小
SHA256
```

如果目标文件存在：

```
跳过
```

后续再考虑 AcoustID。

------

# 48. 文件状态不要依赖数据库

状态根据实际情况动态判断：

```
待处理：
源存在，目标不存在


已完成：
目标存在并且验证通过


失败：
logs中存在失败记录


处理中：
当前任务队列中存在
```

这样即使 Docker 删除、重启：

**不会丢失音乐处理状态。**

------

# 49. Docker重启恢复

程序启动时：

```
扫描所有监控目录
```

自动发现：

```
尚未生成目标文件的音乐
```

重新加入任务队列。

因此：

**不依赖内存任务状态。**

------

# 50. 防止重复转换

必须支持：

```
源文件 + Profile + 文件Hash
```

但由于不使用数据库，可以通过输出文件和 `.musicflow.json` 判断。

例如：

```
song.m4a.musicflow.json
```

内容：

```
{
  "source_hash": "xxx",
  "profile": "Apple Music AAC 256",
  "version": 1,
  "created_at": "2026-08-09T22:00:00"
}
```

这样源文件发生变化后，可以自动重新转换。

------

# 51. Profile版本

这是一个很容易被忽略的问题。

例如以前：

```
Apple Music AAC
256kbps
```

后来修改成：

```
Apple Music AAC
320kbps
```

旧文件不能被认为是最新版本。

因此 Profile 修改后生成：

```
profile_version
```

例如：

```
Apple AAC v1
Apple AAC v2
```

发现旧输出：

```
Profile版本 ≠ 当前版本
```

可以提示：

```
存在旧版本输出
是否重新转换？
```

------

# 52. Apple Music专用模式

提供一个快捷 Profile：

```
Apple Music AAC 256
```

默认：

```
Container:
M4A

Codec:
AAC-LC

Bitrate:
256kbps

Sample Rate:
44100Hz

Channels:
2

Metadata:
保留

Cover:
嵌入

Lyrics:
尽可能保留
```

同时提供：

```
Apple Lossless
```

Profile。

------

# 53. 最终推荐目录

例如：

```
/music
│
├── source
│   ├── FLAC
│   ├── MP3
│   └── Download
│
├── output
│   │
│   ├── apple-aac
│   │   └── Artist
│   │       └── Album
│   │
│   ├── apple-alac
│   │
│   └── mp3
│
└── archive
```

------

# 54. 页面结构

前端建议：

```
Dashboard
│
├── 仪表盘
│
├── 音乐文件
│
├── 转换任务
│
├── 监控目录
│
├── 转换配置
│
├── 规则
│
├── 元数据编辑
│
├── 日志
│
└── 设置
```

------

# 55. 音乐文件页面

支持：

```
搜索
筛选格式
筛选状态
筛选目录
排序
多选
```

搜索：

```
文件名
Artist
Album
Title
```

------

# 56. 规则系统

除了 Profile，还要有“规则”。

例如：

```
如果：

扩展名 = FLAC

且：

采样率 >= 96000

则：

转换为 Apple AAC 256
```

或者：

```
如果：

扩展名 = MP3

则：

不转换
```

或者：

```
如果：

扩展名 = FLAC

则：

同时生成 AAC + ALAC
```

------

# 57. 规则优先级

例如：

```
规则1
FLAC → Apple AAC
优先级100


规则2
MP3 → 不处理
优先级90


规则3
其他音频 → Apple AAC
优先级10
```

从高到低匹配。

------

# 58. 规则动作

支持：

```
转换

跳过

复制

移动

生成多版本
```

------

# 59. 非常重要：不要把“转换”和“整理”强绑定

架构上必须分开：

```
输入文件
   |
   ├── Metadata
   |
   ├── Conversion
   |
   ├── Naming
   |
   ├── Output
   |
   └── Validation
```

这样未来才能扩展。

------

# 60. 未来扩展接口

第一版不要实现，但架构预留：

```
MusicBrainz
Discogs
歌词服务
封面服务
AcoustID
Apple Music相关功能
```

未来可以加入：

```
自动刮削
自动歌词
自动封面
自动识别
```

但第一版不要因此拖慢开发。

------

# 61. 第一阶段必须完成

AI 开发第一阶段只实现：

```
Docker
+
Vue3
+
FastAPI
+
FFmpeg
+
FFprobe
+
Mutagen
+
Watchdog
+
JSON配置
```

功能：

```
文件夹监控
文件扫描
音频信息读取
Metadata读取
Metadata保留
封面保留
AAC
ALAC
MP3
FLAC
M4A
多版本转换
比特率选择
采样率选择
声道选择
输出目录
目录模板
文件名模板
任务队列
并发控制
手动转换
批量转换
任务日志
转换验证
失败重试
Docker部署
```

------

# 62. 第二阶段

再加入：

```
Metadata编辑
封面编辑
歌词
规则系统
高级文件管理
Profile版本
转换前预览
FFmpeg命令预览
```

------

# 63. 第三阶段

最后加入：

```
MusicBrainz
Discogs
AcoustID
自动刮削
自动识别
自动歌词
自动封面
```

------

# 64. AI 开发要求

请严格遵守以下要求：

### 代码质量

- 模块化
- 类型提示
- 异常处理
- 日志完整
- 不允许硬编码路径
- 不允许硬编码 FFmpeg 参数
- 所有用户配置通过 API 管理
- 所有文件操作必须进行路径安全检查

### Docker

必须支持：

```
docker compose up -d
```

直接启动。

------

# 65. 安全要求

尤其注意 NAS 环境。

禁止用户通过 API 任意访问宿主机：

```
../../etc/passwd
```

必须限制文件访问范围。

例如只能访问：

```
/music
/config
/logs
/temp
```

------

# 66. API要求

API必须提供：

```
GET    /api/settings

PUT    /api/settings

GET    /api/profiles

POST   /api/profiles

PUT    /api/profiles/{id}

DELETE /api/profiles/{id}

GET    /api/watch-folders

POST   /api/watch-folders

PUT    /api/watch-folders/{id}

DELETE /api/watch-folders/{id}

GET    /api/files

GET    /api/files/{id}

GET    /api/files/{id}/metadata

PUT    /api/files/{id}/metadata

POST   /api/files/{id}/convert

POST   /api/files/batch-convert

GET    /api/tasks

POST   /api/tasks/{id}/cancel

POST   /api/tasks/{id}/retry

GET    /api/logs
```

------

# 67. 前端要求

页面不能只是简单表单。

要做成真正的 NAS Web 应用。

支持：

```
响应式布局
深色模式
Toast提示
Confirm确认
进度条
实时任务状态
拖拽上传/文件选择
批量选择
分页
搜索
筛选
排序
```

------

# 68. 最终产品定位

最终形成：

```
                 MusicFlow
                     │
        ┌────────────┼────────────┐
        │            │            │
     自动监控      手动管理      转换配置
        │            │            │
        └────────────┼────────────┘
                     │
                 FFmpeg
                     │
        ┌────────────┼────────────┐
        │            │            │
      AAC          ALAC          MP3
     256k           无损          320k
        │            │            │
        └────────────┼────────────┘
                     │
                 输出目录
                     │
              Apple Music
              / Navidrome
              / 其他用途
```

------

## 最重要的几个设计决定

最终我建议你就按这几个原则开发：

**① 不要数据库。**
文件系统 + JSON + 日志即可。

**② 转换 Profile 和规则分开。**
Profile 决定“怎么转”，规则决定“什么时候转”。

**③ 必须支持多版本。**
一个 FLAC 可以一次生成 AAC、ALAC、MP3 等多个版本。

**④ 比特率、采样率、声道、编码器必须全部可配置。**

**⑤ 源文件默认永远不修改、不删除。**

**⑥ 转换完成必须用 FFprobe 二次验证。**

**⑦ 必须有文件稳定检测，避免下载尚未完成就开始转换。**

**⑧ Docker 重启后可以根据文件系统自动恢复，不依赖数据库。**

**⑨ 元数据处理和音频转码分离。**

**⑩ 第一版不要急着接 MusicBrainz。先把“转换引擎”做扎实。**

特别是你的用途，我建议**第一版就把 `Apple Music AAC 256` 和 `Apple Lossless` 做成内置预设**，这样开发完成后你基本可以直接把下载的 FLAC/MP3/M4A 丢进监控目录，然后自动生成 Apple Music 专用文件。

这份需求已经可以直接作为 AI Coding Agent 的 **PRD + 技术设计基线**使用。