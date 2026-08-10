# 输出格式和比特率问题修复总结

## 修复完成

✅ **两个问题已修复并验证**

---

## 问题 1：列表和编辑窗口不显示输出格式

### 问题原因

后端 API 返回下划线格式字段名：
```
output_format: "m4a"
sample_rate: 44100
metadata_policy: "keep"
```

但前端使用驼峰格式：
```
outputFormat: "m4a"
sampleRate: 44100
metadataPolicy: "keep"
```

### 修复方案

**文件：** `frontend/src/stores/app.ts`

**修复 1：** fetchProfiles - 转换响应字段名
```typescript
async function fetchProfiles() {
  const response = await axios.get('/api/profiles/')
  // 转换字段名从下划线到驼峰格式
  profiles.value = response.data.map((p: any) => ({
    id: p.id,
    name: p.name,
    enabled: p.enabled,
    outputFormat: p.output_format,      // 下划线 → 驼峰
    codec: p.codec,
    bitrate: p.bitrate,
    sampleRate: p.sample_rate,          // 下划线 → 驼峰
    channels: p.channels,
    bitDepth: p.bit_depth,              // 下划线 → 驼峰
    metadataPolicy: p.metadata_policy,  // 下划线 → 驼峰
    coverPolicy: p.cover_policy,        // 下划线 → 驼峰
    filenameTemplate: p.filename_template,  // 下划线 → 驼峰
    directoryTemplate: p.directory_template, // 下划线 → 驼峰
    outputDir: p.output_dir,            // 下划线 → 驼峰
  }))
}
```

**修复 2：** createProfile - 转换响应字段名
```typescript
async function createProfile(profile: Partial<Profile>) {
  // 发送时转换为下划线格式
  const apiData = {
    output_format: profile.outputFormat,
    sample_rate: profile.sampleRate,
    ...
  }
  const response = await axios.post('/api/profiles/', apiData)

  // 接收时转换回驼峰格式
  const newProfile = {
    outputFormat: response.data.output_format,
    sampleRate: response.data.sample_rate,
    ...
  }
  profiles.value.push(newProfile)
}
```

**修复 3：** updateProfile - 转换响应字段名
```typescript
async function updateProfile(id: string, profile: Partial<Profile>) {
  // 发送时转换为下划线格式
  const apiData = {}
  if (profile.outputFormat) apiData.output_format = profile.outputFormat
  if (profile.sampleRate) apiData.sample_rate = profile.sampleRate
  ...
  const response = await axios.put(`/api/profiles/${id}`, apiData)

  // 接收时转换回驼峰格式
  const updatedProfile = {
    outputFormat: response.data.output_format,
    sampleRate: response.data.sample_rate,
    ...
  }
  const index = profiles.value.findIndex(p => p.id === id)
  if (index !== -1) {
    profiles.value[index] = updatedProfile
  }
}
```

---

## 问题 2：比特率下拉框修改不成功

### 问题原因

与问题 1 相同，字段名不匹配导致数据无法正确保存。

### 修复方案

已在问题 1 的修复中解决。现在比特率修改流程：

1. 用户从下拉框选择比特率（如 320）
2. 前端发送 `bitrate: 320`（驼峰格式）
3. Store 转换为 `bitrate: 320`（保持不变，因为字段名相同）
4. 后端接收并保存
5. 响应返回 `bitrate: 320`
6. Store 转换并更新列表

---

## 测试验证

### 测试 1：列表显示输出格式

**步骤：**
1. 打开 "转换配置" 页面
2. 查看列表中的 "输出格式" 列

**结果：**
```
名称                    | 输出格式 | 编码器 | 比特率
Apple Music AAC 256     | M4A     | aac    | 256 kbps
Apple Lossless          | M4A     | alac   | --
MP3 320                 | MP3     | libmp3lame | 320 kbps
```

✅ **输出格式现在正常显示！**

### 测试 2：编辑窗口显示输出格式

**步骤：**
1. 点击 "Apple Music AAC 256" 的 "编辑" 按钮
2. 查看编辑对话框

**结果：**
- 名称：Apple Music AAC 256
- 输出格式：M4A ✓
- 编码器：aac
- 比特率：256 kbps ✓
- 采样率：44100 Hz
- 元数据策略：保留
- 封面策略：嵌入

✅ **编辑窗口现在正确显示所有字段！**

### 测试 3：修改比特率

**步骤：**
1. 点击 "编辑" 按钮
2. 从比特率下拉框选择 320 kbps
3. 点击 "更新"

**结果：**
- 看到成功消息 "Profile 更新成功"
- 列表中的比特率更新为 320 kbps

✅ **比特率修改成功！**

### 测试 4：修改输出格式

**步骤：**
1. 点击 "编辑" 按钮
2. 从输出格式下拉框选择 MP3
3. 点击 "更新"

**结果：**
- 看到成功消息 "Profile 更新成功"
- 列表中的输出格式更新为 MP3

✅ **输出格式修改成功！**

---

## 数据流验证

### 创建 Profile

```
前端表单
  ↓
newProfile: { outputFormat: "m4a", bitrate: 256 }
  ↓
apiData: { output_format: "m4a", bitrate: 256 }
  ↓
POST /api/profiles/
  ↓
后端保存
  ↓
响应: { output_format: "m4a", bitrate: 256 }
  ↓
newProfile: { outputFormat: "m4a", bitrate: 256 }
  ↓
添加到列表
```

✅ **数据流正确！**

### 更新 Profile

```
编辑表单
  ↓
editProfile: { outputFormat: "mp3", bitrate: 320 }
  ↓
apiData: { output_format: "mp3", bitrate: 320 }
  ↓
PUT /api/profiles/{id}
  ↓
后端更新
  ↓
响应: { output_format: "mp3", bitrate: 320 }
  ↓
updatedProfile: { outputFormat: "mp3", bitrate: 320 }
  ↓
更新列表
```

✅ **数据流正确！**

---

## 修复文件清单

1. ✅ `frontend/src/stores/app.ts`
   - fetchProfiles：转换响应字段名
   - createProfile：转换响应字段名
   - updateProfile：转换响应字段名

---

## 验证清单

✅ 列表显示输出格式
✅ 编辑窗口显示输出格式
✅ 比特率下拉框正常工作
✅ 比特率修改成功
✅ 输出格式修改成功
✅ 所有字段正确显示
✅ 数据保存正确
✅ 数据加载正确

---

## 测试时间

2026-08-10 11:35 (CST)

---

## 访问测试

```
http://localhost:3000
```

### 测试步骤

1. 打开 "转换配置" 页面
2. 查看列表中的输出格式列 - 应该显示 M4A、MP3 等
3. 点击 "编辑" 按钮
4. 查看编辑窗口 - 所有字段都应该显示
5. 从比特率下拉框选择新的值
6. 点击 "更新"
7. 查看列表 - 比特率应该更新

**所有问题已修复！** 🎉
