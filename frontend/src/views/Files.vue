<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FileItem } from '../types'

const store = useAppStore()
const selectedFiles = ref<FileItem[]>([])
const searchQuery = ref('')
const formatFilter = ref('')
const statusFilter = ref('')
const showDetailDialog = ref(false)
const showConvertDialog = ref(false)
const currentFile = ref<FileItem | null>(null)
const selectedProfile = ref('apple-music-aac-256')

const formats = ['mp3', 'flac', 'm4a', 'aac', 'alac', 'wav', 'ogg', 'opus']
const statuses = [
  { label: '待处理', value: 'pending' },
  { label: '转换中', value: 'converting' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
]

onMounted(() => {
  store.fetchFiles()
  store.fetchProfiles()
})

const handleSelectionChange = (selection: FileItem[]) => {
  selectedFiles.value = selection
}

const formatDuration = (seconds?: number) => {
  if (!seconds) return '--:--'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

const formatSize = (bytes: number) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
}

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    pending: 'warning',
    converting: '',
    completed: 'success',
    failed: 'danger',
  }
  return types[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    pending: '待处理',
    converting: '转换中',
    completed: '已完成',
    failed: '失败',
  }
  return labels[status] || status
}

const handleView = (file: FileItem) => {
  currentFile.value = file
  showDetailDialog.value = true
}

const handleConvert = (file: FileItem) => {
  currentFile.value = file
  showConvertDialog.value = true
}

const executeConvert = async () => {
  if (!currentFile.value || !selectedProfile.value) {
    ElMessage.warning('请选择转换配置')
    return
  }

  try {
    // 构建输出路径
    const outputPath = `D:/Music/output/${currentFile.value.filename.replace('.flac', '.m4a')}`

    // 调用 API 创建转换任务
    const response = await fetch('http://localhost:8082/api/tasks/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_file: currentFile.value.path,
        output_file: outputPath,
        profile_id: selectedProfile.value
      })
    })

    if (response.ok) {
      const task = await response.json()
      ElMessage.success('转换任务已创建')

      // 触发转换引擎执行
      try {
        const convertResponse = await fetch(`http://localhost:8082/api/files/${currentFile.value.id}/convert`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify([selectedProfile.value])
        })

        if (convertResponse.ok) {
          ElMessage.success('转换已启动')
        }
      } catch (err) {
        console.log('Convert trigger response:', err)
      }

      showConvertDialog.value = false
      // 刷新任务列表
      store.fetchTasks()
    } else {
      ElMessage.error('创建转换任务失败')
    }
  } catch (error) {
    ElMessage.error('网络错误')
  }
}

const handleDelete = async (file: FileItem) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除文件 "${file.filename}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    ElMessage.success('文件已删除（实际删除功能待实现）')
  } catch {
    // 用户取消
  }
}

const handleBatchConvert = () => {
  if (selectedFiles.value.length === 0) {
    ElMessage.warning('请先选择文件')
    return
  }
  ElMessage.info(`已选择 ${selectedFiles.value.length} 个文件（批量转换功能待实现）`)
}
</script>

<template>
  <div class="files-page">
    <h1>音乐文件</h1>

    <!-- 搜索和筛选 -->
    <el-card class="filter-card">
      <el-row :gutter="20">
        <el-col :span="8">
          <el-input
            v-model="searchQuery"
            placeholder="搜索文件名、Artist、Album、Title"
            clearable
            prefix-icon="Search"
          />
        </el-col>
        <el-col :span="4">
          <el-select v-model="formatFilter" placeholder="格式" clearable>
            <el-option
              v-for="format in formats"
              :key="format"
              :label="format.toUpperCase()"
              :value="format"
            />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="statusFilter" placeholder="状态" clearable>
            <el-option
              v-for="status in statuses"
              :key="status.value"
              :label="status.label"
              :value="status.value"
            />
          </el-select>
        </el-col>
        <el-col :span="8">
          <el-button type="primary" @click="store.fetchFiles()">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
          <el-button
            type="success"
            :disabled="selectedFiles.length === 0"
            @click="handleBatchConvert"
          >
            <el-icon><VideoPlay /></el-icon>
            批量转换
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 文件列表 -->
    <el-card class="files-card">
      <el-table
        :data="store.files"
        style="width: 100%"
        @selection-change="handleSelectionChange"
        v-loading="store.loading"
      >
        <el-table-column type="selection" width="55" />

        <el-table-column prop="filename" label="文件名" min-width="200" />

        <el-table-column prop="format" label="格式" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.format?.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="size" label="大小" width="100">
          <template #default="{ row }">
            {{ formatSize(row.size) }}
          </template>
        </el-table-column>

        <el-table-column prop="duration" label="时长" width="100">
          <template #default="{ row }">
            {{ formatDuration(row.duration) }}
          </template>
        </el-table-column>

        <el-table-column prop="sampleRate" label="采样率" width="100">
          <template #default="{ row }">
            {{ row.sampleRate ? row.sampleRate + ' Hz' : '--' }}
          </template>
        </el-table-column>

        <el-table-column prop="bitrate" label="比特率" width="100">
          <template #default="{ row }">
            {{ row.bitrate ? (row.bitrate / 1000).toFixed(0) + ' kbps' : '--' }}
          </template>
        </el-table-column>

        <el-table-column prop="artist" label="Artist" width="150" />

        <el-table-column prop="album" label="Album" width="150" />

        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleView(row)">查看</el-button>
            <el-button type="warning" link size="small" @click="handleConvert(row)">转换</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 文件详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      title="文件详情"
      width="600px"
    >
      <div v-if="currentFile" class="file-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="文件名">{{ currentFile.filename }}</el-descriptions-item>
          <el-descriptions-item label="格式">
            <el-tag>{{ currentFile.format?.toUpperCase() }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="大小">{{ formatSize(currentFile.size) }}</el-descriptions-item>
          <el-descriptions-item label="时长">{{ formatDuration(currentFile.duration) }}</el-descriptions-item>
          <el-descriptions-item label="采样率">{{ currentFile.sampleRate ? currentFile.sampleRate + ' Hz' : '--' }}</el-descriptions-item>
          <el-descriptions-item label="比特率">{{ currentFile.bitrate ? (currentFile.bitrate / 1000).toFixed(0) + ' kbps' : '--' }}</el-descriptions-item>
          <el-descriptions-item label="声道">{{ currentFile.channels || '--' }}</el-descriptions-item>
          <el-descriptions-item label="位深">{{ currentFile.bitDepth ? currentFile.bitDepth + ' bit' : '--' }}</el-descriptions-item>
          <el-descriptions-item label="艺术家" :span="2">{{ currentFile.artist || '--' }}</el-descriptions-item>
          <el-descriptions-item label="专辑" :span="2">{{ currentFile.album || '--' }}</el-descriptions-item>
          <el-descriptions-item label="标题" :span="2">{{ currentFile.title || '--' }}</el-descriptions-item>
          <el-descriptions-item label="年份">{{ currentFile.year || '--' }}</el-descriptions-item>
          <el-descriptions-item label="轨道">{{ currentFile.track || '--' }}</el-descriptions-item>
          <el-descriptions-item label="路径" :span="2">
            <span style="word-break: break-all; font-size: 12px;">{{ currentFile.path }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <template #footer>
        <el-button @click="showDetailDialog = false">关闭</el-button>
        <el-button type="primary" @click="handleConvert(currentFile!)">转换</el-button>
      </template>
    </el-dialog>

    <!-- 转换对话框 -->
    <el-dialog
      v-model="showConvertDialog"
      title="转换文件"
      width="500px"
    >
      <div v-if="currentFile">
        <el-form label-width="120px">
          <el-form-item label="源文件">
            <span>{{ currentFile.filename }}</span>
          </el-form-item>
          <el-form-item label="选择配置">
            <el-select v-model="selectedProfile" style="width: 100%">
              <el-option
                v-for="profile in store.profiles"
                :key="profile.id"
                :label="profile.name"
                :value="profile.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="输出路径">
            <span style="color: #666; font-size: 12px;">
              D:/Music/output/{{ currentFile.filename.replace('.flac', '.m4a') }}
            </span>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="showConvertDialog = false">取消</el-button>
        <el-button type="primary" @click="executeConvert">开始转换</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.files-page {
  padding: 0;
}

h1 {
  margin-bottom: 20px;
  color: #303133;
}

.filter-card {
  margin-bottom: 20px;
}

.files-card {
  margin-bottom: 20px;
}

.file-detail {
  padding: 10px;
}
</style>
