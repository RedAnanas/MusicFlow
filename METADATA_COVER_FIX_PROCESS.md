# 元数据和封面修复过程总结

**日期：** 2026-08-10
**状态：** 部分修复完成，待继续

---

## 修复的问题

### 问题 1：元数据丢失

**现象：** 转换后的文件丢失了元数据（如 artist、album、date 等）

**原因：**
- Profile 的 `metadata_policy` 设置为 "keep" 时，元数据复制逻辑没有正确执行
- 某些元数据字段写入失败（如 `track`、`disc`）

**修复状态：** ✅ 已修复

**修复方案：**
- 在 `conversion_engine.py` 中添加详细的元数据复制日志
- 在 `metadata.py` 中添加字段写入的错误处理
- 支持跳过不支持的字段

---

### 问题 2：封面图片丢失

**现象：** 转换后的文件没有封面图片

**原因：**
1. M4A 格式使用错误的方式写入封面
2. FLAC 格式没有正确读取封面
3. `read_metadata` 函数使用 `easy=True` 模式，不读取封面

**修复状态：** ✅ 已修复

**修复方案：**

#### M4A/MP4 格式
```python
# 写入封面
from mutagen.mp4 import MP4Cover
pic = MP4Cover(cover["data"], imageformat=MP4Cover.FORMAT_JPEG)
audio["covr"] = [pic]

# 读取封面
if "covr" in audio.tags:
    pic = audio.tags["covr"][0]
    metadata["cover"] = {
        "data": bytes(pic),
        "mime": "image/jpeg",
        "type": 3
    }
```

#### FLAC/MP3/OGG 格式
```python
# 读取封面
if hasattr(audio, 'pictures') and audio.pictures:
    pic = audio.pictures[0]
    metadata["cover"] = {
        "data": pic.data,
        "mime": pic.mime,
        "type": pic.type
    }
```

---

### 问题 3：元数据读取失败（ValueError）

**现象：** FLAC 文件读取元数据时抛出 `ValueError`

**原因：**
- VorbisComment 对象的 `__contains__` 方法会抛出 ValueError
- 某些格式的 tags 不支持 `in` 操作

**修复状态：** ✅ 已修复

**修复方案：**
```python
# 添加错误处理
try:
    if mutagen_key in audio.tags:
        value = audio.tags[mutagen_key]
        # 处理值...
except (ValueError, TypeError) as e:
    # 某些格式的 tags 不支持 in 操作
    pass
```

---

## 已完成的修复

### 1. 元数据复制逻辑

**文件：** `backend/app/services/conversion_engine.py`

**修改内容：**
- 添加元数据读取详细日志
- 添加元数据字段检查日志
- 添加元数据写入结果日志
- 记录元数据策略状态

### 2. 元数据写入错误处理

**文件：** `backend/app/core/metadata.py`

**修改内容：**
- 添加字段写入错误处理
- 记录写入成功/失败的字段数量
- 支持跳过不支持的字段

### 3. 封面图片写入

**文件：** `backend/app/core/metadata.py`

**修改内容：**
- 为 M4A/MP4 格式使用 `MP4Cover` 写入封面
- 为 FLAC/MP3/OGG 格式使用 `add_picture` 写入封面
- 添加封面写入的错误处理

### 4. 元数据读取

**文件：** `backend/app/core/metadata.py`

**修改内容：**
- 使用非 `easy=True` 模式读取音频文件
- 为 M4A/MP4 格式读取 `covr` 字段的封面
- 为 FLAC/MP3/OGG 格式读取 `pictures` 属性的封面
- 添加 ValueError 异常处理
- 支持多种格式的标签读取

---

## 测试验证

### ✅ M4A 文件测试

```
M4A 文件元数据:
  title: Layers
  artist: 蔡依林
  album: Pleasure
  cover: 有封面 - 1228431 bytes, image/jpeg ✓
```

### ✅ FLAC 文件测试

```
FLAC 文件元数据:
  title: 江南
  artist: 林俊杰
  album: 第二天堂
  cover: 有封面 - 179242 bytes, image/jpeg ✓
```

---

## Git 提交记录

```
90a4368 fix: complete support for FLAC and M4A metadata reading
d3e2c30 fix: support cover image reading for FLAC and other formats
b77f8c3 fix: fix cover image reading and writing for M4A format
9e1b5ac fix: add cover image writing for different audio formats
3a07538 fix: add cover image writing to metadata service
9192417 fix: add error handling and detailed logging for metadata writing
012dfe8 fix: add detailed logging for metadata copy process
```

---

## 待继续的工作

### 1. 验证所有格式的封面写入

需要验证以下格式的封面写入：
- [ ] MP3 格式
- [ ] OGG 格式
- [ ] WAV 格式
- [ ] OPUS 格式

### 2. 测试完整的转换流程

需要测试：
- [ ] FLAC → M4A 转换（包含封面）
- [ ] MP3 → M4A 转换（包含封面）
- [ ] 批量转换（包含封面）

### 3. 优化元数据读取性能

- [ ] 缓存元数据读取结果
- [ ] 减少重复读取
- [ ] 异步读取优化

### 4. 添加单元测试

- [ ] 元数据读取测试
- [ ] 元数据写入测试
- [ ] 封面读取测试
- [ ] 封面写入测试

---

## 下次继续的步骤

### 1. 完成剩余格式的测试

```bash
# 测试 MP3 格式
python -c "
from app.core import metadata_service
metadata = metadata_service.read_metadata('test.mp3')
print(metadata)
"

# 测试 OGG 格式
python -c "
from app.core import metadata_service
metadata = metadata_service.read_metadata('test.ogg')
print(metadata)
"
```

### 2. 测试完整的转换流程

```bash
# 测试 FLAC → M4A 转换
curl -X POST http://localhost:8082/api/tasks/ \
  -H "Content-Type: application/json" \
  -d '{"source_file": "test.flac", "output_file": "test.m4a", "profile_id": "apple-music-aac-256"}'
```

### 3. 验证输出文件的封面

```bash
# 检查输出文件的封面
python -c "
from app.core import metadata_service
metadata = metadata_service.read_metadata('test.m4a')
if metadata and 'cover' in metadata:
    print('有封面')
else:
    print('无封面')
"
```

---

## 相关文件

- `backend/app/core/metadata.py` - 元数据服务
- `backend/app/services/conversion_engine.py` - 转换引擎
- `backend/app/api/routes/tasks.py` - 任务 API

---

## 参考资料

- Mutagen 文档：https://mutagen.readthedocs.io/
- M4A 格式封面：https://mutagen.readthedocs.io/en/latest/user/mp4.html
- FLAC 格式封面：https://mutagen.readthedocs.io/en/latest/user/flac.html

---

**下一步：继续测试其他格式的封面写入，并验证完整的转换流程。**
