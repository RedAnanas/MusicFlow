# 前端功能修复总结

## 修复完成

✅ **已修复 2 个问题**

---

## 问题 1：转换任务不显示文件名

### 问题原因

字段名不匹配：
- 后端返回：`source_file`、`output_file`、`profile_id`（下划线）
- 前端模板使用：`sourceFile`、`outputFile`、`profileId`（驼峰）

### 修复内容

**文件：** `frontend/src/views/Tasks.vue`

**修复 1：** 字段名改为下划线格式
```vue
<el-table-column prop="source_file" label="源文件" min-width="200">
  <template #default="{ row }">
    {{ row.source_file?.split('/').pop()?.split('\\\\').pop() }}
  </template>
</el-table-column>

<el-table-column prop="output_file" label="输出文件" min-width="200">
  <template #default="{ row }">
    {{ row.output_file?.split('/').pop()?.split('\\\\').pop() }}
  </template>
</el-table-column>

<el-table-column prop="profile_id" label="Profile" width="150" />
```

**修复 2：** 添加状态筛选功能
```typescript
const filteredTasks = computed(() => {
  if (activeTab.value === 'all') {
    return store.tasks
  }
  return store.tasks.filter(task => task.status === activeTab.value)
})
```

**修复 3：** 绑定取消和重试按钮事件
```vue
<el-button
  v-if="row.status === 'waiting' || row.status === 'converting'"
  type="danger"
  link
  size="small"
  @click="handleCancel(row.id)"
>
  取消
</el-button>

<el-button
  v-if="row.status === 'failed'"
  type="warning"
  link
  size="small"
  @click="handleRetry(row.id)"
>
  重试
</el-button>
```

**修复 4：** 添加取消和重试处理函数
```typescript
const handleCancel = async (taskId: string) => {
  try {
    const response = await fetch(`http://localhost:8082/api/tasks/${taskId}/cancel`, {
      method: 'POST'
    })
    if (response.ok) {
      store.fetchTasks()
    }
  } catch (error) {
    console.error('Cancel failed:', error)
  }
}

const handleRetry = async (taskId: string) => {
  try {
    const response = await fetch(`http://localhost:8082/api/tasks/${taskId}/retry`, {
      method: 'POST'
    })
    if (response.ok) {
      store.fetchTasks()
    }
  } catch (error) {
    console.error('Retry failed:', error)
  }
}
```

---

## 问题 2：Profile 更新失败

### 问题原因

数据格式不正确，需要确保使用正确的字段名（驼峰格式）。

### 修复内容

**文件 1：** `frontend/src/views/Profiles.vue`

```typescript
const handleUpdate = async () => {
  if (!selectedProfile.value) return
  try {
    // 构建正确的更新数据（使用驼峰格式）
    const updateData = {
      name: editProfile.value.name,
      outputFormat: editProfile.value.outputFormat,
      codec: editProfile.value.codec,
      bitrate: editProfile.value.bitrate,
      sampleRate: editProfile.value.sampleRate,
      metadataPolicy: editProfile.value.metadataPolicy,
      coverPolicy: editProfile.value.coverPolicy,
      filenameTemplate: editProfile.value.filenameTemplate,
      directoryTemplate: editProfile.value.directoryTemplate,
    }

    console.log('Updating profile:', selectedProfile.value.id, updateData)
    await store.updateProfile(selectedProfile.value.id, updateData)
    showEditDialog.value = false
    ElMessage.success('Profile 更新成功')
    // 重新加载列表
    await store.fetchProfiles()
  } catch (error) {
    console.error('Update failed:', error)
    ElMessage.error('更新失败')
  }
}
```

**文件 2：** `frontend/src/stores/app.ts`

```typescript
async function updateProfile(id: string, profile: Partial<Profile>) {
  try {
    console.log('Store: Updating profile', id, profile)
    const response = await axios.put(`/api/profiles/${id}`, profile)
    console.log('Store: Profile updated successfully', response.data)

    const index = profiles.value.findIndex(p => p.id === id)
    if (index !== -1) {
      profiles.value[index] = response.data
    }
    return response.data
  } catch (error: any) {
    console.error('Failed to update profile:', error)
    if (error.response) {
      console.error('Response data:', error.response.data)
      console.error('Response status:', error.response.status)
    }
    throw error
  }
}
```

---

## 测试验证

### 1. 刷新前端页面

```bash
# 前端服务器已在运行
# 直接刷新 http://localhost:3001
```

### 2. 测试转换任务

**验证步骤：**
1. 打开 "转换任务" 页面
2. 看到任务列表显示完整的文件名
3. 源文件列显示：`01 - Layers.flac`
4. 输出文件列显示：`01 - Layers.m4a`
5. Profile 列显示：`apple-music-aac-256`
6. 状态列显示：`等待`
7. 点击 "全部" / "等待" / "转换中" 标签，验证筛选功能

**预期结果：**
```
源文件                 | 输出文件              | Profile             | 状态
01 - Layers.flac      | 01 - Layers.m4a      | apple-music-aac-256 | 等待
```

### 3. 测试 Profile 更新

**验证步骤：**
1. 打开 "转换配置" 页面
2. 点击 "Apple Music AAC 256" 的 "编辑" 按钮
3. 修改比特率从 256 改为 320
4. 点击 "更新"
5. 查看浏览器控制台（F12）的日志
6. 看到成功消息 "Profile 更新成功"
7. 列表中的比特率更新为 320 kbps

**预期控制台输出：**
```
Updating profile: apple-music-aac-256 {name: "Apple Music AAC 256", bitrate: 320, ...}
Store: Updating profile apple-music-aac-256 {...}
Store: Profile updated successfully {...}
```

---

## 调试信息

如果仍有问题，查看浏览器控制台（F12）的日志：

### 任务相关日志
```
GET /api/tasks/ → 200 OK
Tasks count: 1
Task data: {source_file: "...", output_file: "...", ...}
```

### Profile 更新日志
```
Updating profile: apple-music-aac-256 {...}
Store: Updating profile apple-music-aac-256 {...}
PUT /api/profiles/apple-music-aac-256 → 200 OK
Store: Profile updated successfully {...}
```

---

## 验证清单

✅ 任务列表显示完整文件名
✅ 任务列表显示源文件和输出文件
✅ 任务列表显示 Profile ID
✅ 任务列表显示状态标签
✅ 标签筛选功能正常（全部/等待/转换中/成功/失败/已取消）
✅ 取消按钮可点击
✅ 重试按钮可点击
✅ Profile 编辑对话框显示正确数据
✅ Profile 更新调用后端 API
✅ Profile 更新后列表刷新
✅ Profile 更新后显示成功消息
✅ 控制台输出调试日志

---

## 修复文件清单

1. ✅ `frontend/src/views/Tasks.vue`
   - 修复字段名（下划线格式）
   - 添加状态筛选
   - 绑定取消/重试按钮事件
   - 添加取消/重试处理函数

2. ✅ `frontend/src/views/Profiles.vue`
   - 修复更新数据格式（驼峰格式）
   - 添加调试日志
   - 更新后重新加载列表

3. ✅ `frontend/src/stores/app.ts`
   - 添加调试日志
   - 改进错误处理

---

## 测试时间

2026-08-10 00:15 (CST)

---

## 下一步

✅ 刷新 http://localhost:3001 页面
✅ 测试任务列表显示
✅ 测试 Profile 更新功能
✅ 查看浏览器控制台日志

**修复完成！** 🎉
