# MusicFlow 问题修复记录

**记录时间：** 2026-08-10
**当前状态：** 问题 1–6 已修复，问题 7 待修复

---

## 未修复问题清单

### 问题 1：转换配置 - 比特率和编码器下拉框（✅ 已修复）

**描述：** 转换配置页面的比特率和编码器应该是下拉框，可以筛选

**期望行为：**
- 比特率：下拉框选择（64-320 kbps）
- 编码器：下拉框选择（可搜索筛选）

**当前状态：** ✅ 已修复并验证

**相关文件：**
- `frontend/src/views/Profiles.vue` - 添加了 bitrateOptions 和 codecOptions
- `frontend/src/stores/app.ts` - 字段映射

**修复思路：**
```vue
<!-- 比特率下拉框 -->
<el-select v-model="editProfile.bitrate">
  <el-option v-for="option in bitrateOptions" :key="option.value" :label="option.label" :value="option.value" />
</el-select>

<!-- 编码器下拉框（可搜索）-->
<el-select v-model="editProfile.codec" filterable>
  <el-option v-for="option in codecOptions" :key="option.value" :label="option.label" :value="option.value" />
</el-select>
```

**验证方法：**
1. 打开转换配置页面
2. 点击编辑按钮
3. 检查比特率和编码器是否为下拉框

---

### 问题 2：转换配置 - 输出格式字段不显示（✅ 已修复）

**描述：** 列表中应该显示输出格式字段

**期望行为：**
- 列表中显示 "输出格式" 列
- 显示格式标签（如 M4A、MP3）

**当前状态：** ✅ 已修复并验证

**相关文件：**
- `frontend/src/views/Profiles.vue` - outputFormat 列

**修复思路：**
```vue
<el-table-column prop="outputFormat" label="输出格式" width="120">
  <template #default="{ row }">
    <el-tag>{{ row.outputFormat?.toUpperCase() }}</el-tag>
  </template>
</el-table-column>
```

**验证方法：**
1. 打开转换配置页面
2. 检查列表是否显示输出格式列

---

### 问题 3：转换配置 - 版本字段不需要（✅ 已修复）

**描述：** 列表中不应该显示版本字段

**期望行为：**
- 移除版本列显示

**当前状态：** ✅ 已移除版本列

**相关文件：**
- `frontend/src/views/Profiles.vue` - 已移除版本列

**验证方法：**
1. 打开转换配置页面
2. 检查列表是否没有版本列

---

### 问题 4：转换配置 - 新建功能失效（✅ 已修复）

**描述：** 创建新配置时显示"创建失败"

**期望行为：**
- 成功创建配置
- 显示成功消息

**当前状态：** ✅ 已修复并验证

**相关文件：**
- `frontend/src/stores/app.ts` - createProfile 方法
- `frontend/src/views/Profiles.vue` - handleCreate 方法

**修复思路：**
```typescript
// 在 store 中确保字段名转换正确
async function createProfile(profile: Partial<Profile>) {
  const apiData = {
    name: profile.name,
    output_format: profile.outputFormat,  // 驼峰 → 下划线
    codec: profile.codec,
    bitrate: profile.bitrate,
    // ...
  }
  const response = await axios.post('/api/profiles/', apiData)
  // ...
}
```

**验证方法：**
1. 打开转换配置页面
2. 点击创建按钮
3. 填写信息
4. 点击创建
5. 检查控制台是否有错误

---

### 问题 5：监控目录 - 创建失败（✅ 已修复）

**描述：** 创建监控目录时没有发送请求

**期望行为：**
- 成功创建监控目录
- 显示成功消息

**当前状态：** ✅ 已修复并验证

**相关文件：**
- `frontend/src/stores/app.ts` - createWatchFolder 方法
- `frontend/src/views/WatchFolders.vue` - handleCreate 方法
- `backend/app/api/routes/watch_folders.py` - POST 端点

**修复思路：**
```typescript
// 前端 store
async function createWatchFolder(folder: Partial<WatchFolder>) {
  const apiData = {
    name: folder.name,
    input_dir: folder.inputDir,  // 驼峰 → 下划线
    profile_ids: folder.profileIds,
    auto_process: folder.autoProcess,
    recursive_scan: folder.recursiveScan,
    scan_interval_minutes: folder.scanIntervalMinutes,
    output_dir: folder.outputDir,
  }
  const response = await axios.post('/api/watch-folders/', apiData)
  // ...
}
```

**验证方法：**
1. 打开监控目录页面
2. 点击添加目录按钮
3. 填写信息
4. 点击创建
5. 打开浏览器开发者工具 (F12)
6. 查看 Console 和 Network 标签
7. 检查是否有请求发出

---

### 问题 6：监控目录 - 编辑失败（✅ 已修复）

**描述：** 编辑监控目录时显示"更新失败"

**期望行为：**
- 成功更新监控目录
- 显示成功消息

**当前状态：** ✅ 已修复并验证

**相关文件：**
- `frontend/src/stores/app.ts` - updateWatchFolder 方法
- `frontend/src/views/WatchFolders.vue` - handleUpdate 方法
- `backend/app/api/routes/watch_folders.py` - PUT 端点

**修复思路：**
```typescript
// 前端 store
async function updateWatchFolder(id: string, folder: Partial<WatchFolder>) {
  const apiData = {}
  if (folder.name) apiData.name = folder.name
  if (folder.inputDir) apiData.input_dir = folder.inputDir
  if (folder.profileIds) apiData.profile_ids = folder.profileIds
  // ...
  const response = await axios.put(`/api/watch-folders/${id}`, apiData)
  // ...
}

# 后端 - 使用 WatchFolderUpdate 模型（所有字段可选）
class WatchFolderUpdate(BaseModel):
    name: Optional[str] = None
    input_dir: Optional[str] = None
    profile_ids: Optional[List[str]] = None
    # ...
```

**验证方法：**
1. 打开监控目录页面
2. 点击编辑按钮
3. 修改信息
4. 点击更新
5. 打开浏览器开发者工具 (F12)
6. 查看 Console 和 Network 标签
7. 检查是否有请求发出

---

### 问题 7：元数据丢失（⚠️ 待修复）

**描述：** 转换后的文件丢失了元数据（只保留了歌词）

**期望行为：**
- 转换后的文件包含完整的元数据
- 包括 artist、album、date、cover 等

**当前状态：** ⚠️ 部分修复，但可能未完全生效

**相关文件：**
- `backend/app/core/metadata.py` - 元数据读写
- `backend/app/services/conversion_engine.py` - 转换引擎

**修复思路：**

**1. 元数据复制逻辑：**
```python
# 在 conversion_engine.py 中
if profile.metadata_policy.value == "keep":
    metadata = metadata_service.read_metadata(task.source_file)
    if metadata:
        metadata_service.write_metadata(task.output_file, metadata)
```

**2. 元数据写入（带错误处理）：**
```python
# 在 metadata.py 中
def write_metadata(self, file_path: str, metadata: Dict) -> bool:
    audio = MutagenFile(file_path, easy=True)
    
    # 写入文本字段
    for field in self.METADATA_FIELDS:
        if field in metadata and metadata[field] is not None:
            try:
                audio[field] = metadata[field]
            except Exception as e:
                logger.warning(f"Could not write field '{field}': {e}")
                continue
    
    # 写入封面图片
    if "cover" in metadata and metadata["cover"]:
        cover = metadata["cover"]
        if "data" in cover and "mime" in cover:
            try:
                if file_ext in [".m4a", ".mp4"]:
                    from mutagen.mp4 import MP4Cover
                    pic = MP4Cover(cover["data"], imageformat=MP4Cover.FORMAT_JPEG)
                    audio["covr"] = [pic]
                elif file_ext in [".mp3", ".flac", ".ogg"]:
                    from mutagen.flac import Picture
                    pic = Picture()
                    pic.type = 3
                    pic.mime = cover["mime"]
                    pic.data = cover["data"]
                    audio.add_picture(pic)
            except Exception as e:
                logger.warning(f"Could not write cover: {e}")
    
    audio.save()
    return True
```

**3. 元数据读取（支持多种格式）：**
```python
# 在 metadata.py 中
def read_metadata(self, file_path: str) -> Optional[Dict]:
    # 使用非 easy=True 模式读取
    audio = MutagenFile(file_path)
    
    metadata = {}
    
    # 读取文本标签
    if hasattr(audio, 'tags') and audio.tags:
        # M4A/MP4 格式
        for tag_key, mutagen_key in [("title", "©nam"), ("artist", "©ART"), ...]:
            try:
                if mutagen_key in audio.tags:
                    metadata[tag_key] = str(audio.tags[mutagen_key][0])
            except (ValueError, TypeError):
                pass
        
        # FLAC/MP3/OGG 格式
        flac_tags = {"title": "title", "artist": "artist", ...}
        for tag_key, mutagen_key in flac_tags.items():
            try:
                if mutagen_key in audio.tags:
                    metadata[tag_key] = str(audio.tags[mutagen_key][0])
            except (ValueError, TypeError):
                pass
    
    # 读取封面
    if hasattr(audio, 'pictures') and audio.pictures:
        pic = audio.pictures[0]
        metadata["cover"] = {
            "data": pic.data,
            "mime": pic.mime,
            "type": pic.type
        }
    elif "covr" in audio.tags:
        pic = audio.tags["covr"][0]
        metadata["cover"] = {
            "data": bytes(pic),
            "mime": "image/jpeg",
            "type": 3
        }
    
    return metadata
```

**验证方法：**
1. 转换一个 FLAC 文件到 M4A
2. 检查输出文件的元数据
3. 检查输出文件的封面图片

---

## 调试步骤

### 步骤 1：打开浏览器开发者工具

按 **F12** 或右键点击页面 → 选择 "检查"

### 步骤 2：查看 Console 标签

检查是否有错误信息：
```
❌ 创建失败
❌ 更新失败
❌ 请求未发送
```

### 步骤 3：查看 Network 标签

1. 点击 "Network" 标签
2. 勾选 "Preserve log"
3. 执行操作（创建/编辑）
4. 检查是否有请求发出
5. 如果有请求，查看响应状态码

### 步骤 4：检查后端日志

```bash
# 查看后端日志
tail -100 D:/Documents/AI/MusicFlow/backend/logs/app.log
```

---

## 相关文件清单

### 前端文件
- `frontend/src/views/Profiles.vue` - 转换配置页面
- `frontend/src/views/WatchFolders.vue` - 监控目录页面
- `frontend/src/stores/app.ts` - 状态管理
- `frontend/src/types/index.ts` - 类型定义

### 后端文件
- `backend/app/api/routes/profiles.py` - Profile API
- `backend/app/api/routes/watch_folders.py` - 监控目录 API
- `backend/app/core/metadata.py` - 元数据服务
- `backend/app/services/conversion_engine.py` - 转换引擎

---

## 已验证的功能

✅ 后端 API 正常工作
✅ 前端页面加载正常
✅ 转换功能正常
✅ 任务持久化正常
✅ 监控目录列表显示正常

---

## 建议的修复顺序

1. **先修复前端问题**（比特率、编码器、输出格式下拉框）
2. **再修复 API 调用问题**（监控目录创建、编辑）
3. **最后修复元数据问题**（确保完整复制）

---

## 参考资料

- Element Plus 文档：https://element-plus.org/
- Mutagen 文档：https://mutagen.readthedocs.io/
- Vue 3 文档：https://vuejs.org/

---

**下次使用其他工具时，可以直接参考这个文档进行修复！** 📝
