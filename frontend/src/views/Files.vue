<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
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
const selectedFolder = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const showDetailDialog = ref(false)
const showConvertDialog = ref(false)
const currentFile = ref<FileItem | null>(null)
const conversionFiles = ref<FileItem[]>([])
const selectedProfile = ref('apple-music-aac-256')
const outputDir = ref('')

const formats = ['mp3', 'flac', 'm4a', 'aac', 'alac', 'wav', 'ogg', 'opus']
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
    const fileDirectory = getDirectoryPath(file.path)
    const matchesFolder = !selectedDirectory ||
      fileDirectory === selectedDirectory ||
      fileDirectory.startsWith(directoryPrefix)
    return matchesKeyword && matchesFormat && matchesFolder
  })
})

const paginatedFiles = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredFiles.value.slice(start, start + pageSize.value)
})

watch([searchQuery, formatFilter, selectedFolder], () => {
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

const handleView = (file: FileItem) => {
  currentFile.value = file
  showDetailDialog.value = true
}

const handleConvert = (file: FileItem) => {
  currentFile.value = file
  conversionFiles.value = [file]
  outputDir.value = ''
  showConvertDialog.value = true
}

const executeConvert = async () => {
  if (!currentFile.value || !selectedProfile.value) {
    ElMessage.warning('请选择转换配置')
    return
  }

  try {
    const response = await axios.post('/api/files/batch-convert', {
      file_ids: conversionFiles.value.map(file => file.id),
      profile_id: selectedProfile.value,
      output_dir: outputDir.value.trim() || null,
    })

    const created = response.data.converted.filter((item: { status: string }) => item.status === 'queued').length
    if (created) {
      ElMessage.success(`已创建 ${created} 个转换任务`)
    } else {
      ElMessage.info('未创建新任务，目标文件或活动任务已存在')
    }
    if (response.data.errors.length) {
      ElMessage.warning(`${response.data.errors.length} 个文件创建任务失败`)
    }
      showConvertDialog.value = false
      await store.fetchTasks()
  } catch (error) {
    ElMessage.error('创建转换任务失败')
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
  currentFile.value = selectedFiles.value[0]
  conversionFiles.value = [...selectedFiles.value]
  outputDir.value = ''
  showConvertDialog.value = true
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
        <el-col :span="12">
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
      :title="conversionFiles.length > 1 ? `批量转换（${conversionFiles.length} 个文件）` : '转换文件'"
      width="500px"
    >
      <div v-if="currentFile">
        <el-form label-width="120px">
          <el-form-item label="源文件">
            <span v-if="conversionFiles.length === 1">{{ currentFile.filename }}</span>
            <span v-else>已选择 {{ conversionFiles.length }} 个文件</span>
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
            <el-input v-model="outputDir" placeholder="留空则使用全局输出目录" clearable />
            <div style="color: #666; font-size: 12px; margin-top: 4px;">可填写 WSL 绝对目录，例如 /mnt/d/Music/output/M4A/AAC/Converted</div>
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
