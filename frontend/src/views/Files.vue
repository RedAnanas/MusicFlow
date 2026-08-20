<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import TablePagination from '../components/TablePagination.vue'
import type { FileItem } from '../types'

interface FolderTreeNode {
  label: string
  path: string
  children?: FolderTreeNode[]
}

const store = useAppStore()
const selectedFiles = ref<FileItem[]>([])
const searchQuery = ref('')
const formatFilter = ref('')
const statusFilter = ref('')
const selectedFolder = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
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
const folderTreeProps = {
  children: 'children',
  label: 'label',
}

onMounted(() => {
  store.fetchFiles()
  store.fetchProfiles()
})

const normalizePath = (path: string) => {
  const normalizedPath = path.replace(/\\/g, '/')
  const trimmedPath = normalizedPath.replace(/\/+$/, '')
  return trimmedPath || (normalizedPath.startsWith('/') ? '/' : '')
}

const getDirectoryPath = (path: string) => {
  const normalizedPath = normalizePath(path)
  const separatorIndex = normalizedPath.lastIndexOf('/')
  if (separatorIndex < 0) return normalizedPath
  return separatorIndex === 0 ? '/' : normalizedPath.slice(0, separatorIndex)
}

const getCommonDirectory = (directories: string[]) => {
  const splitDirectories = directories.map(directory => normalizePath(directory).split('/'))
  const shortestLength = Math.min(...splitDirectories.map(parts => parts.length))
  let commonLength = 0

  while (
    commonLength < shortestLength &&
    splitDirectories.every(parts => parts[commonLength] === splitDirectories[0][commonLength])
  ) {
    commonLength += 1
  }

  const commonDirectory = splitDirectories[0].slice(0, commonLength).join('/')
  return commonDirectory || (directories[0].startsWith('/') ? '/' : '')
}

const folderTree = computed<FolderTreeNode[]>(() => {
  const directories = [...new Set(store.files.map(file => getDirectoryPath(file.path)))]
  const allFilesNode: FolderTreeNode = {
    label: `全部文件（${store.files.length}）`,
    path: '',
    children: [],
  }
  if (!directories.length) return [allFilesNode]

  const commonRoot = getCommonDirectory(directories)
  const rootLabel = commonRoot.split('/').filter(Boolean).pop() || commonRoot || '根目录'
  const rootNode: FolderTreeNode = {
    label: rootLabel,
    path: commonRoot,
    children: [],
  }

  for (const directory of directories) {
    const relativePath = directory.slice(commonRoot.length).replace(/^\/+/, '')
    if (!relativePath) continue

    let parentPath = commonRoot
    let childNodes = rootNode.children!
    for (const segment of relativePath.split('/').filter(Boolean)) {
      const nodePath = parentPath === '/'
        ? `/${segment}`
        : parentPath
          ? `${parentPath}/${segment}`
          : segment
      let childNode = childNodes.find(node => node.path === nodePath)
      if (!childNode) {
        childNode = { label: segment, path: nodePath, children: [] }
        childNodes.push(childNode)
      }
      parentPath = nodePath
      childNodes = childNode.children!
    }
  }

  allFilesNode.children = [rootNode]
  return [allFilesNode]
})

const filteredFiles = computed(() => {
  const keyword = searchQuery.value.trim().toLowerCase()
  const selectedDirectory = normalizePath(selectedFolder.value)
  const directoryPrefix = selectedDirectory.endsWith('/')
    ? selectedDirectory
    : `${selectedDirectory}/`

  return store.files.filter(file => {
    const matchesKeyword = !keyword || [file.filename, file.artist, file.album, file.title]
      .some(value => (value || '').toLowerCase().includes(keyword))
    const matchesFormat = !formatFilter.value || file.format === formatFilter.value
    const matchesStatus = !statusFilter.value || file.status === statusFilter.value
    const fileDirectory = getDirectoryPath(file.path)
    const matchesFolder = !selectedDirectory ||
      fileDirectory === selectedDirectory ||
      fileDirectory.startsWith(directoryPrefix)
    return matchesKeyword && matchesFormat && matchesStatus && matchesFolder
  })
})

const paginatedFiles = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredFiles.value.slice(start, start + pageSize.value)
})

watch([searchQuery, formatFilter, statusFilter, selectedFolder], () => {
  currentPage.value = 1
  selectedFiles.value = []
})

watch(currentPage, () => {
  selectedFiles.value = []
})

watch(() => filteredFiles.value.length, total => {
  const lastPage = Math.max(1, Math.ceil(total / pageSize.value))
  if (currentPage.value > lastPage) currentPage.value = lastPage
})

const handleSelectionChange = (selection: FileItem[]) => {
  selectedFiles.value = selection
}

const handleFolderSelect = (folder: FolderTreeNode) => {
  selectedFolder.value = folder.path
}

const handleSizeChange = () => {
  currentPage.value = 1
  selectedFiles.value = []
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
    const outputPath = `/mnt/d/Music/output/${currentFile.value.filename.replace('.flac', '.m4a')}`

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
      `确定要从磁盘永久删除文件“${file.filename}”吗？删除后无法恢复。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await store.deleteFile(file.id)
    selectedFiles.value = selectedFiles.value.filter(item => item.id !== file.id)
    ElMessage.success('文件已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    console.error('Delete file failed:', error)
    ElMessage.error('文件删除失败')
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
            placeholder="搜索文件名、艺术家、专辑、标题"
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
      <div class="files-layout">
        <aside class="folder-panel">
          <div class="folder-title">文件夹</div>
          <el-tree
            :data="folderTree"
            :props="folderTreeProps"
            node-key="path"
            default-expand-all
            highlight-current
            empty-text="暂无文件夹"
            @node-click="handleFolderSelect"
          />
        </aside>

        <div class="files-table-panel">
          <el-table
            class="files-table"
            :data="paginatedFiles"
            style="width: 100%"
            @selection-change="handleSelectionChange"
            v-loading="store.loading"
          >
            <el-table-column type="selection" width="55" />

            <el-table-column label="序号" width="60" align="center">
              <template #default="{ $index }">
                {{ (currentPage - 1) * pageSize + $index + 1 }}
              </template>
            </el-table-column>

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

            <el-table-column prop="artist" label="艺术家" width="150" />

            <el-table-column prop="album" label="专辑" width="150" />

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

          <TablePagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="filteredFiles.length"
            @size-change="handleSizeChange"
          />
        </div>
      </div>
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
              /mnt/d/Music/output/{{ currentFile.filename.replace('.flac', '.m4a') }}
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

.files-layout {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.folder-panel {
  flex: 0 0 220px;
  max-height: calc(100vh - 260px);
  padding-right: 12px;
  overflow: auto;
  border-right: 1px solid #ebeef5;
}

.folder-title {
  margin-bottom: 10px;
  color: #303133;
  font-weight: 600;
}

.files-table-panel {
  flex: 1;
  min-width: 0;
}

:deep(.files-table .el-scrollbar__bar.is-vertical) {
  display: none;
}

:deep(.files-table .el-scrollbar__wrap) {
  overflow-y: hidden;
}

.file-detail {
  padding: 10px;
}

@media (max-width: 1000px) {
  .files-layout {
    flex-direction: column;
  }

  .folder-panel {
    width: 100%;
    max-height: 220px;
    padding-right: 0;
    padding-bottom: 12px;
    border-right: none;
    border-bottom: 1px solid #ebeef5;
  }
}
</style>
