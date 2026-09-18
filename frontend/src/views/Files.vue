<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import TablePagination from '../components/TablePagination.vue'
import ServerFileBrowser from '../components/ServerFileBrowser.vue'
import type { DeliveryTarget, FileItem } from '../types'

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
const conversionTargets = ref<DeliveryTarget[]>([])
const coverErrors = ref(new Set<string>())
const showFileBrowser = ref(false)
const showOutputBrowser = ref(false)
const outputTargetIndex = ref<number | null>(null)
const browserMode = ref<'files' | 'directory'>('files')
const importing = ref(false)
const isMobile = ref(false)
const mobileVisibleCount = ref(20)
const mobileSelectionMode = ref(false)
const syncMobile = () => { isMobile.value = window.innerWidth <= 700 }

const formats = ['mp3', 'flac', 'm4a', 'aac', 'alac', 'wav', 'ogg', 'opus']
const folderTreeProps = {
  children: 'children',
  label: 'label',
}

const conversionTotalSize = computed(() => conversionFiles.value.reduce((total, file) => total + file.size, 0))
const conversionTotalDuration = computed(() => conversionFiles.value.reduce((total, file) => total + (file.duration || 0), 0))
const conversionReady = computed(() => conversionTargets.value.length > 0 && conversionTargets.value.every(target => {
  return Boolean(target.outputDir.trim()) && (target.type === 'copy' || Boolean(target.profileId))
}))
const deliverySummary = computed(() => conversionTargets.value.map(target => {
  if (target.type === 'copy') return '原样复制'
  return `转换输出：${store.profiles.find(profile => profile.id === target.profileId)?.name || '未选择方案'}`
}))

const removeConversionFile = (id: string) => {
  conversionFiles.value = conversionFiles.value.filter(file => file.id !== id)
  currentFile.value = conversionFiles.value[0] || null
  if (!conversionFiles.value.length) showConvertDialog.value = false
}

const createDefaultDeliveryTarget = (): DeliveryTarget => ({
  type: 'convert',
  profileId: selectedProfile.value,
  outputDir: '',
})

const addDeliveryTarget = () => {
  conversionTargets.value.push(createDefaultDeliveryTarget())
}

const removeDeliveryTarget = (index: number) => {
  conversionTargets.value.splice(index, 1)
}

onMounted(() => {
  syncMobile()
  window.addEventListener('resize', syncMobile)
  window.addEventListener('scroll', loadMoreMobileFiles, { passive: true })
  store.fetchFiles()
  store.fetchProfiles()
  store.fetchLibrarySources()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', syncMobile)
  window.removeEventListener('scroll', loadMoreMobileFiles)
})

watch(
  () => store.profiles,
  profiles => {
    if (profiles.length && !profiles.some(profile => profile.id === selectedProfile.value)) {
      selectedProfile.value = profiles[0].id
    }
  },
  { immediate: true, deep: true },
)

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
  if (isMobile.value) return filteredFiles.value.slice(0, mobileVisibleCount.value)
  const start = (currentPage.value - 1) * pageSize.value
  return filteredFiles.value.slice(start, start + pageSize.value)
})

watch([searchQuery, formatFilter, selectedFolder], () => {
  currentPage.value = 1
  mobileVisibleCount.value = 20
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

const toggleMobileSelection = (file: FileItem, checked: boolean) => {
  selectedFiles.value = checked
    ? [...selectedFiles.value.filter(item => item.id !== file.id), file]
    : selectedFiles.value.filter(item => item.id !== file.id)
}

const loadMoreMobileFiles = () => {
  if (!isMobile.value || mobileVisibleCount.value >= filteredFiles.value.length) return
  if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 220) {
    mobileVisibleCount.value += 20
  }
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

const getCoverUrl = (file: FileItem) => `/api/files/${file.id}/cover`

const markCoverError = (fileId: string) => {
  coverErrors.value.add(fileId)
  coverErrors.value = new Set(coverErrors.value)
}

const handleView = (file: FileItem) => {
  currentFile.value = file
  showDetailDialog.value = true
}

const handleConvert = (file: FileItem) => {
  currentFile.value = file
  conversionFiles.value = [file]
  conversionTargets.value = [createDefaultDeliveryTarget()]
  showConvertDialog.value = true
}

const executeConvert = async () => {
  if (!conversionFiles.value.length || !conversionReady.value) {
    ElMessage.warning('请完整配置输出规则')
    return
  }

  try {
    const response = await axios.post('/api/files/batch-deliver', {
      file_ids: conversionFiles.value.map(file => file.id),
      targets: conversionTargets.value.map(target => ({
        type: target.type,
        output_dir: target.outputDir.trim(),
        profile_id: target.type === 'convert' ? target.profileId : null,
      })),
    })

    const created = response.data.deliveries.filter((item: { status: string }) => item.status === 'queued').length
    const copied = response.data.deliveries.filter((item: { status: string }) => item.status === 'copied').length
    if (created) {
      ElMessage.success(`已创建 ${created} 个转换任务`)
    }
    if (copied) ElMessage.success(`已原样复制 ${copied} 个文件`)
    if (!created && !copied) ElMessage.info('目标文件或活动任务已存在，未创建新内容')
    if (response.data.errors.length) {
      ElMessage.warning(`${response.data.errors.length} 条输出规则执行失败`)
    }
    showConvertDialog.value = false
    await store.fetchTasks()
  } catch (error) {
    ElMessage.error('执行输出规则失败')
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
  conversionTargets.value = [createDefaultDeliveryTarget()]
  showConvertDialog.value = true
}

const openFileBrowser = (mode: 'files' | 'directory') => {
  browserMode.value = mode
  showFileBrowser.value = true
}

const handleImportPaths = async (paths: string[]) => {
  importing.value = true
  try {
    const result = await store.importFiles(paths)
    if (result.imported.length) ElMessage.success(`已加入 ${result.imported.length} 个音频文件`)
    else ElMessage.info('所选位置没有发现新的支持格式音频')
    if (result.errors.length) ElMessage.warning(`${result.errors.length} 个路径无法加入`)
  } catch (error) {
    const message = axios.isAxiosError(error) ? error.response?.data?.detail : null
    ElMessage.error(message || '添加音乐失败')
  } finally {
    importing.value = false
  }
}

const handleRemoveSource = async (id: string, path: string) => {
  try {
    await ElMessageBox.confirm(
      `确定停止读取“${path}”吗？磁盘上的文件和文件夹不会被删除。`,
      '移除音乐库来源',
      { confirmButtonText: '停止读取', cancelButtonText: '取消', type: 'warning' },
    )
    await store.removeLibrarySource(id)
    ElMessage.success('已停止读取该位置，磁盘内容未删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error('移除音乐库来源失败')
  }
}

const selectOutputDirectory = (paths: string[]) => {
  if (outputTargetIndex.value === null) return
  conversionTargets.value[outputTargetIndex.value].outputDir = paths[0] || ''
}
</script>

<template>
  <div class="files-page product-page">
    <section class="workbench-shell">
      <header class="workbench-toolbar">
        <div class="toolbar-path">
          <el-button circle text aria-label="返回上级" @click="selectedFolder = ''"><el-icon><Back /></el-icon></el-button>
          <span class="toolbar-divider"></span>
          <el-icon><FolderOpened /></el-icon>
          <strong>{{ selectedFolder ? selectedFolder.split('/').filter(Boolean).pop() : '根目录' }}</strong>
        </div>
        <div class="toolbar-controls">
          <el-button circle text aria-label="刷新文件" :loading="store.loading" @click="store.fetchFiles(true)"><el-icon><Refresh /></el-icon></el-button>
          <el-button circle text aria-label="重置清单视图" @click="currentPage = 1"><el-icon><Operation /></el-icon></el-button>
          <el-select v-model="formatFilter" clearable placeholder="筛选" aria-label="按格式筛选">
            <el-option v-for="format in formats" :key="format" :label="format.toUpperCase()" :value="format" />
          </el-select>
          <el-input v-model="searchQuery" clearable placeholder="搜索文件或文件夹" aria-label="搜索文件或文件夹">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-button circle text aria-label="系统设置"><el-icon><Setting /></el-icon></el-button>
        </div>
      </header>

      <div class="workbench-layout">
        <aside class="folder-panel">
          <div class="folder-panel-heading"><strong>文件夹</strong><span>选择要处理的内容</span></div>
          <div class="library-sources">
            <div v-for="source in store.librarySources" :key="source.id" class="library-source" :class="{ offline: !source.exists }">
              <span class="source-check"></span><el-icon><FolderOpened v-if="source.is_directory" /><Document v-else /></el-icon>
              <span :title="source.path">{{ source.path }}</span>
              <em>{{ store.files.filter(file => file.path.startsWith(source.path)).length }}</em>
              <el-button type="danger" link aria-label="停止读取" @click="handleRemoveSource(source.id, source.path)"><el-icon><Close /></el-icon></el-button>
            </div>
            <span v-if="!store.librarySources.length" class="source-empty">尚未添加文件夹</span>
          </div>
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

        <main class="workbench-content">
          <section class="files-table-panel">
            <div class="file-list-heading"><div><span>音乐清单</span><strong>{{ filteredFiles.length }} 首音乐</strong></div><div v-if="isMobile" class="mobile-selection-state"><span v-if="mobileSelectionMode">已选 {{ selectedFiles.length }} 首</span><el-button link @click="mobileSelectionMode = !mobileSelectionMode; !mobileSelectionMode && (selectedFiles = [])">{{ mobileSelectionMode ? '完成' : '多选' }}</el-button></div></div>
          <el-table
            class="files-table"
            :data="paginatedFiles"
            style="width: 100%"
            @selection-change="handleSelectionChange"
            v-loading="store.loading"
          >
            <el-table-column v-if="!isMobile" type="selection" width="55" />

            <el-table-column label="文件信息" :min-width="isMobile ? 0 : 230">
              <template #default="{ row }">
                <div class="track-cell">
                  <el-checkbox v-if="isMobile && mobileSelectionMode" :model-value="selectedFiles.some(file => file.id === row.id)" aria-label="选择当前音乐" @change="toggleMobileSelection(row, Boolean($event))" />
                  <span class="cover-thumb">
                    <img v-if="!coverErrors.has(row.id)" :src="getCoverUrl(row)" :alt="`${row.album || row.filename} 封面`" loading="lazy" @error="markCoverError(row.id)" />
                    <el-icon v-else><Headset /></el-icon>
                  </span>
                  <span class="track-copy">
                    <strong>{{ row.title || row.filename }}</strong>
                    <small>{{ row.artist || '未知艺术家' }} · {{ row.album || '未知专辑' }}</small>
                    <el-tag v-if="isMobile" size="small" class="mobile-format-tag">{{ row.format?.toUpperCase() }}</el-tag>
                  </span>
                </div>
              </template>
            </el-table-column>

            <el-table-column v-if="!isMobile" prop="format" label="格式" width="72">
              <template #default="{ row }">
                <el-tag size="small">{{ row.format?.toUpperCase() }}</el-tag>
              </template>
            </el-table-column>

            <el-table-column v-if="!isMobile" prop="size" label="大小" width="78">
              <template #default="{ row }">
                {{ formatSize(row.size) }}
              </template>
            </el-table-column>

            <el-table-column v-if="!isMobile" prop="duration" label="时长" width="72">
              <template #default="{ row }">
                {{ formatDuration(row.duration) }}
              </template>
            </el-table-column>

            <el-table-column label="操作" :width="isMobile ? 128 : 148">
              <template #default="{ row }">
                <div class="file-row-actions"><el-button type="primary" link size="small" @click="handleView(row)">查看</el-button><el-button type="warning" link size="small" @click="handleConvert(row)">转换</el-button><el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button></div>
              </template>
            </el-table-column>
          </el-table>

          <TablePagination
            v-if="!isMobile"
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="filteredFiles.length"
            @size-change="handleSizeChange"
          />
          <p v-else class="mobile-load-state">{{ mobileVisibleCount < filteredFiles.length ? '继续下滑加载更多' : `已显示全部 ${filteredFiles.length} 首音乐` }}</p>
          </section>
        </main>
      </div>

      <nav class="workbench-actions" aria-label="文件操作">
        <el-tooltip content="添加文件" placement="top"><el-button circle @click="openFileBrowser('files')"><el-icon><DocumentAdd /></el-icon></el-button></el-tooltip>
        <el-tooltip content="添加文件夹" placement="top"><el-button circle @click="openFileBrowser('directory')"><el-icon><FolderAdd /></el-icon></el-button></el-tooltip>
        <el-tooltip content="回到音乐清单第一页" placement="top"><el-button circle @click="currentPage = 1"><el-icon><Files /></el-icon></el-button></el-tooltip>
        <el-tooltip content="刷新" placement="top"><el-button circle @click="store.fetchFiles(true)"><el-icon><Refresh /></el-icon></el-button></el-tooltip>
        <el-tooltip content="转换已选音乐" placement="top"><el-button circle :disabled="selectedFiles.length === 0" @click="handleBatchConvert"><el-icon><VideoPlay /></el-icon></el-button></el-tooltip>
        <el-tooltip content="查看详情" placement="top"><el-button circle :disabled="!currentFile" @click="showDetailDialog = true"><el-icon><Document /></el-icon></el-button></el-tooltip>
        <el-tooltip content="移除当前音乐" placement="top"><el-button circle :disabled="!currentFile" @click="currentFile && handleDelete(currentFile)"><el-icon><Delete /></el-icon></el-button></el-tooltip>
        <el-tooltip content="更多操作" placement="top"><el-button class="is-active" circle><el-icon><MoreFilled /></el-icon></el-button></el-tooltip>
        <el-tooltip content="清除选择" placement="top"><el-button circle :disabled="!currentFile" @click="currentFile = null"><el-icon><Close /></el-icon></el-button></el-tooltip>
      </nav>
    </section>

    <!-- 文件详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      title="文件详情"
      width="600px"
      class="file-detail-dialog"
    >
      <div v-if="currentFile" class="file-detail">
        <div class="detail-summary"><span class="detail-cover"><img v-if="!coverErrors.has(currentFile.id)" :src="getCoverUrl(currentFile)" :alt="`${currentFile.album || currentFile.filename} 封面`" @error="markCoverError(currentFile.id)" /><el-icon v-else><Headset /></el-icon></span><div><strong>{{ currentFile.title || currentFile.filename }}</strong><span>{{ currentFile.artist || '未知艺术家' }} · {{ currentFile.album || '未知专辑' }}</span></div></div>
        <el-descriptions :column="2" border class="file-descriptions">
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
      :title="conversionFiles.length > 1 ? '创建批量转换任务' : '创建转换任务'"
      width="1140px"
      class="workspace-dialog conversion-dialog"
      destroy-on-close
    >
      <div v-if="currentFile" class="conversion-workspace">
        <section class="conversion-files-panel">
          <div class="conversion-panel-heading"><div><strong>已选择文件</strong><span>{{ conversionFiles.length }} 首音乐</span></div><el-button v-if="conversionFiles.length > 1" link type="primary" @click="conversionFiles = []">清空</el-button></div>
          <div class="conversion-file-list">
            <div v-for="file in conversionFiles" :key="file.id" class="conversion-file-row">
              <span class="conversion-cover"><img v-if="!coverErrors.has(file.id)" :src="getCoverUrl(file)" :alt="`${file.album || file.filename} 封面`" @error="markCoverError(file.id)" /><el-icon v-else><Headset /></el-icon></span>
              <div><strong>{{ file.title || file.filename }}</strong><span>{{ file.artist || '未知艺术家' }} · {{ file.album || '未知专辑' }}</span><small>{{ file.format.toUpperCase() }} · {{ formatSize(file.size) }} · {{ formatDuration(file.duration) }}</small></div>
              <el-button circle text aria-label="移除文件" @click="removeConversionFile(file.id)"><el-icon><Close /></el-icon></el-button>
            </div>
          </div>
          <div class="selection-summary"><div><span>总大小</span><strong>{{ formatSize(conversionTotalSize) }}</strong></div><div><span>总时长</span><strong>{{ formatDuration(conversionTotalDuration) }}</strong></div></div>
        </section>

        <section class="conversion-settings-panel">
          <div class="conversion-stepper"><span class="done"><i>1</i>选择内容</span><b></b><span class="active"><i>2</i>输出规则</span><b></b><span><i>3</i>确认提交</span></div>
          <div class="settings-heading"><div><strong>输出规则</strong><span>与监控目录一致，可同时转换和原样复制</span></div><el-tag effect="plain">{{ conversionTargets.length }} 条规则</el-tag></div>
          <div class="delivery-rule-list">
            <section v-for="(target, index) in conversionTargets" :key="index" class="delivery-rule-card">
              <div class="delivery-rule-head"><strong>规则 {{ index + 1 }} · {{ target.type === 'convert' ? '转换输出' : '原样复制' }}</strong><el-button v-if="conversionTargets.length > 1" link type="danger" @click="removeDeliveryTarget(index)">删除</el-button></div>
              <el-form label-position="top" class="delivery-target-form">
                <el-form-item label="处理方式"><el-radio-group v-model="target.type"><el-radio value="convert">转换输出</el-radio><el-radio value="copy">原样复制</el-radio></el-radio-group></el-form-item>
                <el-form-item v-if="target.type === 'convert'" label="转换方案" required><el-select v-model="target.profileId" placeholder="请选择转换方案"><el-option v-for="profile in store.profiles" :key="profile.id" :label="profile.name" :value="profile.id" /></el-select></el-form-item>
                <el-form-item label="输出目录" required><el-input v-model="target.outputDir" readonly placeholder="请选择输出目录"><template #append><el-button @click="outputTargetIndex = index; showOutputBrowser = true"><el-icon><FolderOpened /></el-icon>选择</el-button></template></el-input><small>{{ target.type === 'convert' ? '按方案转换后输出；同名目标或活动任务会安全跳过。' : '保留原文件格式、标签和文件名；同名文件不会覆盖。' }}</small></el-form-item>
              </el-form>
            </section>
            <el-button plain class="add-delivery-rule" @click="addDeliveryTarget"><el-icon><Plus /></el-icon>添加输出规则</el-button>
          </div>
          <div class="output-estimate"><div><el-icon><Document /></el-icon><span>文件数<strong>{{ conversionFiles.length }}</strong></span></div><div><el-icon><Files /></el-icon><span>源文件大小<strong>{{ formatSize(conversionTotalSize) }}</strong></span></div><div><el-icon><Timer /></el-icon><span>总时长<strong>{{ formatDuration(conversionTotalDuration) }}</strong></span></div><div><el-icon><Connection /></el-icon><span>输出规则<strong>{{ conversionTargets.length }}</strong></span></div></div>
          <div class="duplicate-warning"><el-icon><WarningFilled /></el-icon><span>转换和复制会并行执行；同名文件、已有目标和活动任务都会安全跳过，不会覆盖现有文件。</span></div>
          <div class="delivery-preview"><strong>本次将执行</strong><span v-for="summary in deliverySummary" :key="summary">{{ summary }}</span></div>
        </section>
      </div>
      <template #footer><div class="conversion-footer"><span>将按 {{ conversionTargets.length }} 条输出规则处理 {{ conversionFiles.length }} 首音乐</span><div><el-button @click="showConvertDialog = false">取消</el-button><el-button type="primary" :disabled="!conversionFiles.length || !conversionReady" @click="executeConvert">执行 {{ conversionTargets.length }} 条输出规则</el-button></div></div></template>
    </el-dialog>

    <ServerFileBrowser
      v-model="showFileBrowser"
      :mode="browserMode"
      @select="handleImportPaths"
    />
    <ServerFileBrowser v-model="showOutputBrowser" mode="directory" @select="selectOutputDirectory" />
  </div>
</template>

<style scoped>
.files-page {
  min-height: calc(100vh - 118px);
  width: calc(100vw - 24px);
  max-width: none;
  padding: 0;
  margin-top: -12px;
  margin-left: calc((100% - 100vw) / 2 + 12px);
}

.workbench-shell {
  position: relative;
  min-height: calc(100vh - 128px);
  overflow: hidden;
  background: rgba(255, 255, 255, .9);
  border: 1px solid #edf0f5;
  border-radius: 22px;
  box-shadow: 0 16px 35px rgba(44, 51, 72, .05);
}

.workbench-toolbar {
  display: flex;
  height: 66px;
  align-items: center;
  justify-content: space-between;
  padding: 0 17px;
  border-bottom: 1px solid #edf0f4;
}

.toolbar-path, .toolbar-controls { display: flex; align-items: center; }
.toolbar-path { gap: 10px; color: #313c4f; }
.toolbar-path strong { font-size: 14px; font-weight: 750; }
.toolbar-path > .el-icon { color: #758093; font-size: 18px; }
.toolbar-divider { width: 1px; height: 24px; background: #edf0f4; }
.toolbar-controls { gap: 9px; }
.toolbar-controls :deep(.el-button) { width: 40px; height: 40px; color: #6f7a8a; background: #fbfcfe; border: 1px solid #edf0f4; }
.toolbar-controls :deep(.el-select) { width: 112px; }
.toolbar-controls :deep(.el-select__wrapper), .toolbar-controls :deep(.el-input__wrapper) { min-height: 40px; background: #fbfcfe; box-shadow: 0 0 0 1px #e6eaf0 inset; border-radius: 14px; }
.toolbar-controls :deep(.el-input) { width: 280px; }

.workbench-layout { display: flex; min-height: calc(100vh - 194px); }

.folder-panel {
  flex: 0 0 470px;
  padding: 24px 16px 28px 26px;
  overflow: auto;
  border-right: 1px solid #e7ebf1;
}

.folder-panel-heading { display: flex; align-items: baseline; justify-content: space-between; padding: 0 8px 15px; border-bottom: 1px solid #e8ebf0; }
.folder-panel-heading strong { color: #465166; font-size: 15px; font-weight: 750; }
.folder-panel-heading span { color: #a3aab8; font-size: 12px; }
.library-sources { display: flex; flex-direction: column; gap: 5px; padding: 15px 5px 10px; }
.library-source { display: grid; grid-template-columns: 20px 22px minmax(0, 1fr) auto 22px; gap: 8px; align-items: center; min-height: 35px; padding: 0 7px 0 2px; color: #69758a; border-radius: 8px; font-size: 13px; }
.library-source:hover { background: #f7f5ff; }.library-source > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.library-source > .el-icon { color: #738097; font-size: 18px; }.library-source em { min-width: 28px; padding: 4px 7px; color: #657187; background: #f8f9fb; border-radius: 999px; font-size: 11px; font-style: normal; font-weight: 700; text-align: center; }.source-check { width: 18px; height: 18px; border: 1px solid #dce2eb; border-radius: 7px; }.library-source.offline { color: #a45f58; background: #fff4f3; }.source-empty { display: block; padding: 18px 9px; color: #a3aab8; font-size: 12px; }

.workbench-content { display: flex; flex: 1; min-width: 0; padding: 26px; }

.workbench-actions { position: absolute; z-index: 2; bottom: 17px; left: 50%; display: flex; gap: 10px; padding: 10px; background: rgba(255, 255, 255, .95); border: 1px solid #ebedf2; border-radius: 20px; box-shadow: 0 12px 28px rgba(54, 61, 80, .10); transform: translateX(-50%); }.workbench-actions :deep(.el-button) { width: 50px; height: 50px; margin: 0; color: #778293; background: #fff; border-color: #e5e9ef; }.workbench-actions :deep(.el-button:hover) { color: #9a73ef; border-color: #cfc0fa; }.workbench-actions :deep(.el-button.is-active) { color: white; background: #a881f3; border-color: #a881f3; }.workbench-actions :deep(.el-button.is-disabled) { opacity: .45; }

.files-table-panel { display: flex; width: 100%; min-width: 0; flex-direction: column; padding: 0 8px 92px; }.file-list-heading { display: flex; align-items: center; justify-content: space-between; padding: 0 6px 17px; }.file-list-heading > div { display: flex; gap: 9px; align-items: baseline; }.file-list-heading span { color: #273248; font-size: 20px; font-weight: 800; }.file-list-heading strong { color: #a881f3; font-size: 12px; }.files-table { flex: 1; overflow: hidden; border: 1px solid #edf0f4; border-radius: 16px; }

.track-cell { display: flex; width: 100%; gap: 11px; align-items: center; padding: 0; color: inherit; }.cover-thumb { display: grid; flex: 0 0 auto; width: 42px; height: 42px; place-items: center; overflow: hidden; color: #9d79eb; background: #f0ebfc; border-radius: 10px; }.cover-thumb img { width: 100%; height: 100%; object-fit: cover; }.track-copy { display: flex; min-width: 0; flex-direction: column; gap: 3px; }.track-copy strong, .track-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.track-copy strong { color: #2b3548; font-size: 14px; font-weight: 650; }.track-copy small { color: #8b95a5; font-size: 12px; }.mobile-load-state { margin: 14px 0 0; color: #9aa2b1; font-size: 12px; text-align: center; }
.file-row-actions { display: flex; gap: 9px; align-items: center; justify-content: flex-end; white-space: nowrap; }.file-row-actions .el-button + .el-button { margin-left: 0; }

:deep(.folder-panel .el-tree) { padding: 2px 5px; color: #778397; background: transparent; }:deep(.folder-panel .el-tree-node__content) { height: 35px; border-radius: 8px; }:deep(.folder-panel .el-tree-node__content:hover), :deep(.folder-panel .is-current > .el-tree-node__content) { color: #7655bf; background: #eee9ff; }:deep(.files-table .el-scrollbar__bar.is-vertical) { display: none; }:deep(.files-table .el-scrollbar__wrap) { overflow-y: hidden; }

html.dark .workbench-shell { background: rgb(29 34 46 / 94%); border-color: #3a4152; box-shadow: 0 16px 35px rgb(0 0 0 / 20%); }
html.dark .workbench-toolbar, html.dark .folder-panel, html.dark .folder-panel-heading, html.dark .files-table { border-color: #3a4152; }
html.dark .toolbar-path, html.dark .folder-panel-heading strong, html.dark .file-list-heading span, html.dark .track-copy strong { color: #eef1f7; }
:global(html.dark) .toolbar-controls :deep(.el-button), :global(html.dark) .toolbar-controls :deep(.el-select__wrapper), :global(html.dark) .toolbar-controls :deep(.el-input__wrapper) { color: #d8deea; background: #262c3a; box-shadow: 0 0 0 1px #41495b inset; border-color: #41495b; }
html.dark .toolbar-divider, html.dark .folder-panel-heading { border-color: #3a4152; background: #3a4152; }
html.dark .folder-panel-heading { background: transparent; }
html.dark .library-source, html.dark .track-copy small, html.dark .folder-panel-heading span { color: #aeb8c9; }
:global(html.dark) .library-source:hover, :global(html.dark) .folder-panel :deep(.el-tree-node__content:hover), :global(html.dark) .folder-panel :deep(.is-current > .el-tree-node__content) { background: #302c44; }
html.dark .library-source em { color: #c4ccda; background: #2a303f; }
html.dark .workbench-actions { background: rgb(37 43 57 / 96%); border-color: #41495b; box-shadow: 0 12px 28px rgb(0 0 0 / 28%); }
:global(html.dark) .workbench-actions :deep(.el-button) { color: #b9c3d3; background: #262c3a; border-color: #41495b; }

@media (max-width: 1180px) { .folder-panel { flex-basis: 285px; }.toolbar-controls :deep(.el-input) { width: 200px; } }
@media (max-width: 820px) { .files-page { padding: 6px; }.workbench-toolbar { height: auto; min-height: 64px; gap: 8px; flex-wrap: wrap; padding: 10px; }.toolbar-controls { width: 100%; justify-content: flex-end; }.toolbar-controls :deep(.el-input) { width: min(100%, 230px); }.toolbar-controls :deep(.el-select) { width: 94px; }.workbench-layout { display: block; }.folder-panel { max-height: 220px; border-right: 0; border-bottom: 1px solid #e7ebf1; }.workbench-content { min-height: 520px; padding: 18px; }.workbench-actions { gap: 6px; max-width: calc(100% - 20px); overflow-x: auto; }.workbench-actions :deep(.el-button) { width: 44px; height: 44px; flex: 0 0 auto; } }

/* 保留转换对话框的原有布局。 */
.legacy-layout-placeholder {
  display: none;
}

.file-detail {
  padding: 10px;
}
.detail-summary { display: flex; gap: 13px; align-items: center; padding: 15px; margin-bottom: 14px; background: #faf9fd; border: 1px solid #ebe8f3; border-radius: 14px; }.detail-cover { display: grid; width: 56px; height: 56px; flex: 0 0 56px; place-items: center; overflow: hidden; color: #9d79eb; background: #f0ebfc; border-radius: 13px; }.detail-cover img { width: 100%; height: 100%; object-fit: cover; }.detail-summary > div { display: flex; min-width: 0; flex-direction: column; gap: 5px; }.detail-summary strong, .detail-summary span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.detail-summary strong { color: #354057; font-size: 15px; }.detail-summary > div > span { color: #8490a2; font-size: 12px; }
:global(.file-detail-dialog) { max-height: calc(100dvh - 32px); margin: 16px auto !important; border-radius: 20px; }.file-detail-dialog :deep(.el-dialog__body) { max-height: calc(100dvh - 192px); overflow-y: auto; }.file-detail-dialog :deep(.el-dialog__footer) { border-top: 1px solid #ececf2; }

.conversion-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 20px;
}

.conversion-form :deep(.el-form-item) {
  min-width: 0;
  margin-bottom: 18px;
}

.conversion-form :deep(.el-form-item__label) {
  width: auto !important;
  height: auto;
  padding: 0 0 8px;
  color: #303133;
  font-weight: 500;
  line-height: 20px;
}

.conversion-item-full {
  grid-column: 1 / -1;
}

.conversion-section-title {
  grid-column: 1 / -1;
  margin: 4px 0 14px;
  padding-left: 10px;
  color: #0c9c68;
  border-left: 3px solid #0c9c68;
  font-size: 15px;
  font-weight: 600;
  line-height: 20px;
}

.conversion-field-help {
  margin-left: 4px;
  color: #909399;
  cursor: help;
  vertical-align: -2px;
}

.conversion-workspace { display: grid; grid-template-columns: 340px minmax(0, 1fr); min-height: 620px; }
.conversion-files-panel { display: flex; min-width: 0; flex-direction: column; background: #fbfaff; border-right: 1px solid #ece9f5; }
.conversion-panel-heading { display: flex; align-items: center; justify-content: space-between; padding: 22px 23px; border-bottom: 1px solid #ece9f5; }.conversion-panel-heading > div { display: flex; flex-direction: column; gap: 4px; }.conversion-panel-heading strong { color: #303a50; font-size: 15px; }.conversion-panel-heading span { color: #9ca4b4; font-size: 11px; }
.conversion-file-list { flex: 1; max-height: 505px; overflow: auto; }.conversion-file-row { display: flex; align-items: center; gap: 11px; padding: 15px 18px; border-bottom: 1px solid #f0eef5; }.conversion-cover { display: grid; width: 49px; height: 49px; flex: 0 0 49px; place-items: center; overflow: hidden; color: #9c79eb; background: #f0ebfc; border-radius: 11px; }.conversion-cover img { width: 100%; height: 100%; object-fit: cover; }.conversion-file-row > div { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 3px; }.conversion-file-row strong, .conversion-file-row span, .conversion-file-row small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.conversion-file-row strong { color: #354057; font-size: 12px; }.conversion-file-row span { color: #7f899a; font-size: 11px; }.conversion-file-row small { color: #a2a9b7; font-size: 10px; }.selection-summary { display: grid; grid-template-columns: 1fr 1fr; padding: 15px 19px; border-top: 1px solid #ece9f5; }.selection-summary div { display: flex; flex-direction: column; gap: 3px; }.selection-summary span { color: #9ca4b4; font-size: 10px; }.selection-summary strong { color: #455168; font-size: 12px; }
.conversion-settings-panel { min-width: 0; padding: 28px 30px; }.conversion-stepper { display: flex; align-items: center; margin-bottom: 25px; color: #abb1bf; font-size: 11px; }.conversion-stepper span { display: flex; align-items: center; gap: 7px; white-space: nowrap; }.conversion-stepper i { display: grid; width: 24px; height: 24px; place-items: center; font-style: normal; border: 1px solid #e1e4eb; border-radius: 50%; }.conversion-stepper b { flex: 1; height: 1px; margin: 0 11px; background: #e8e9ef; }.conversion-stepper .done, .conversion-stepper .active { color: #8d69df; font-weight: 750; }.conversion-stepper .done i { color: #fff; background: #a881f3; border-color: #a881f3; }.conversion-stepper .active i { border-color: #a881f3; }
.settings-heading { display: flex; align-items: flex-start; justify-content: space-between; padding-bottom: 17px; border-bottom: 1px solid #ececf2; }.settings-heading > div { display: flex; flex-direction: column; gap: 5px; }.settings-heading strong { color: #303a50; font-size: 18px; }.settings-heading span { color: #929bac; font-size: 11px; }.settings-heading :deep(.el-tag) { color: #8b67dc; background: #f4f0ff; border-color: #dfd4fc; }
.delivery-rule-list { display: flex; flex-direction: column; gap: 12px; padding-top: 17px; }.delivery-rule-card { padding: 16px; background: #faf9fd; border: 1px solid #ebe8f3; border-radius: 13px; }.delivery-rule-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; color: #49546a; font-size: 13px; }.delivery-target-form { display: grid; grid-template-columns: .8fr 1.15fr; gap: 12px 16px; }.delivery-target-form :deep(.el-form-item) { margin-bottom: 0; }.delivery-target-form :deep(.el-select) { width: 100%; }.delivery-target-form :deep(.el-radio.is-checked .el-radio__label) { color: #8b67dc; }.delivery-target-form :deep(.el-radio__input.is-checked .el-radio__inner) { background: #a881f3; border-color: #a881f3; }.delivery-target-form :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e3e5ec inset; }.delivery-target-form small { display: block; margin-top: 6px; color: #98a0af; font-size: 10px; }.add-delivery-rule { align-self: flex-start; color: #8b67dc; border-color: #dcd0fb; }
.output-estimate { display: grid; grid-template-columns: repeat(4, 1fr); padding: 16px 0; margin-top: 17px; border-top: 1px solid #ececf2; border-bottom: 1px solid #ececf2; }.output-estimate > div { display: flex; align-items: center; justify-content: center; gap: 7px; color: #a881f3; border-right: 1px solid #ececf2; }.output-estimate > div:last-child { border-right: 0; }.output-estimate span { display: flex; flex-direction: column; gap: 3px; color: #9aa2b1; font-size: 10px; }.output-estimate strong { color: #455168; font-size: 12px; }.duplicate-warning { display: flex; align-items: flex-start; gap: 8px; padding: 12px 14px; margin: 15px 0; color: #a2772d; background: #fff8e9; border: 1px solid #f4e2bd; border-radius: 10px; font-size: 11px; line-height: 1.55; }.delivery-preview { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 13px 14px; color: #677287; background: #f7f6fa; border-radius: 10px; font-size: 11px; }.delivery-preview strong { color: #465168; }.delivery-preview span { padding: 4px 8px; color: #8563d3; background: #eee8ff; border-radius: 999px; }
.naming-preview { padding: 13px; background: #f7f9f8; border-radius: 9px; }.naming-preview > div { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }.naming-preview strong { color: #405048; font-size: 11px; }.naming-preview span { color: #98a19d; font-size: 9px; }.naming-preview code { display: block; padding: 5px 7px; overflow: hidden; color: #5b6862; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }.naming-preview code + code { border-top: 1px solid #e5eae7; }.advanced-summary { margin-top: 11px; border: 0; }.advanced-summary :deep(.el-collapse-item__header) { height: 38px; padding: 0 10px; color: #64716b; background: #f7f9f8; border: 0; border-radius: 8px; font-size: 10px; }.advanced-summary :deep(.el-collapse-item__wrap) { border: 0; }.advanced-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding-top: 9px; }.advanced-grid span { display: flex; flex-direction: column; gap: 3px; color: #929c97; font-size: 9px; }.advanced-grid strong { color: #3d4b44; font-size: 10px; }.conversion-footer { display: flex; align-items: center; justify-content: space-between; }.conversion-footer > span { color: #7f8b85; font-size: 11px; }

@media (max-width: 1000px) {
  :global(.conversion-dialog) { width: calc(100vw - 32px) !important; max-width: calc(100vw - 32px); }
  .conversion-workspace { grid-template-columns: 1fr; }
  .conversion-files-panel { display: none; }
  .delivery-target-form { grid-template-columns: 1fr; }
  .output-estimate { grid-template-columns: 1fr 1fr; gap: 12px 0; }
  .output-estimate > div:nth-child(2) { border-right: 0; }
}

:global(.conversion-dialog) { display: flex; max-height: calc(100dvh - 32px); flex-direction: column; margin: 16px auto !important; }
:global(.conversion-dialog .el-dialog__header), :global(.conversion-dialog .el-dialog__footer) { flex: 0 0 auto; }
:global(.conversion-dialog .el-dialog__body) { min-height: 0; padding: 0; overflow: auto; }

@media (max-width: 700px) {
  .files-page { min-height: auto; width: 100%; margin: 0; padding: 0; }
  .workbench-shell { min-height: auto; border-radius: 18px; }
  .workbench-toolbar { align-items: flex-start; min-height: 106px; padding: 12px; }
  .toolbar-path { min-height: 36px; }
  .toolbar-controls { justify-content: space-between; gap: 7px; }
  .toolbar-controls :deep(.el-input) { flex: 1; width: auto; min-width: 0; }
  .toolbar-controls :deep(.el-select) { width: 82px; }
  .toolbar-controls :deep(.el-button) { width: 36px; height: 36px; }
  .folder-panel { max-height: 185px; padding: 17px 12px; }
  .folder-panel-heading { padding-bottom: 11px; }
  .library-sources { padding-top: 10px; }
  .workbench-content { min-height: 440px; padding: 16px 10px 92px; }
  .files-table-panel { padding: 0 0 84px; }
  .file-list-heading { padding: 0 5px 12px; }
  .file-list-heading span { font-size: 18px; }
  .mobile-selection-state { gap: 8px !important; }.mobile-selection-state > span { color: #8b67dc; font-size: 12px; font-weight: 650; }.mobile-selection-state :deep(.el-button) { padding: 0; color: #8b67dc; }
  .track-cell { gap: 9px; }
  .track-cell :deep(.el-checkbox) { flex: 0 0 auto; }.track-cell :deep(.el-checkbox__inner) { width: 18px; height: 18px; border-radius: 6px; }.track-cell :deep(.el-checkbox__input.is-checked .el-checkbox__inner) { background: #a881f3; border-color: #a881f3; }
  .cover-thumb { width: 50px; height: 50px; border-radius: 12px; }
  .track-copy strong { font-size: 13px; }
  .track-copy small { max-width: 175px; font-size: 11px; }
  .mobile-format-tag { align-self: flex-start; margin-top: 2px; color: #8b67dc; background: #f4f0ff; border-color: #dfd4fc; }
  .files-table { border-radius: 14px; }
  :deep(.files-table .el-table__cell) { padding: 10px 5px; }
  .file-row-actions { gap: 7px; justify-content: flex-start; }
  .workbench-actions { position: fixed; z-index: 19; bottom: calc(66px + env(safe-area-inset-bottom)); left: 50%; width: fit-content; max-width: calc(100% - 24px); padding: 7px; margin: 0; overflow: visible; transform: translateX(-50%); border-radius: 18px; }
  .workbench-actions :deep(.el-button) { width: 40px; height: 40px; }
  :global(.conversion-dialog) { width: calc(100vw - 24px) !important; max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); margin: 12px auto !important; border-radius: 18px; }
  :global(.conversion-dialog .el-dialog__header) { padding: 18px 18px 14px; margin-right: 0; }
  :global(.conversion-dialog .el-dialog__title) { font-size: 17px; }
  :global(.conversion-dialog .el-dialog__headerbtn) { top: 16px; right: 14px; }
  :global(.conversion-dialog .el-dialog__body) { overflow-y: auto; }
  :global(.conversion-dialog .el-dialog__footer) { padding: 12px 16px calc(12px + env(safe-area-inset-bottom)); border-top: 1px solid #ececf2; }
  .conversion-workspace { min-height: 0; }
  .conversion-settings-panel { padding: 18px; }
  .conversion-stepper { margin-bottom: 18px; font-size: 10px; }
  .conversion-stepper b { margin: 0 7px; }
  .conversion-stepper i { width: 22px; height: 22px; }
  .settings-heading { padding-bottom: 14px; }
  .settings-heading strong { font-size: 17px; }
  .settings-heading span { max-width: 230px; line-height: 1.4; }
  .delivery-rule-list { padding-top: 14px; }
  .delivery-rule-card { padding: 15px; }
  .delivery-target-form { gap: 4px; }
  .delivery-target-form :deep(.el-form-item__label) { padding-bottom: 5px; }
  .delivery-target-form :deep(.el-radio) { margin-right: 14px; }
  .output-estimate { margin-top: 14px; padding: 13px 0; }
  .output-estimate > div { justify-content: flex-start; padding-left: 10px; }
  .duplicate-warning { margin: 13px 0; padding: 11px; }
  .delivery-preview { padding: 11px; }
  .conversion-footer { gap: 10px; }
  .conversion-footer > span { display: none; }
  .conversion-footer > div { display: flex; flex: 1; gap: 8px; }
  .conversion-footer :deep(.el-button) { flex: 1; min-width: 0; margin: 0; }
  :global(.file-detail-dialog) { width: calc(100vw - 24px) !important; max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); margin: 12px auto !important; border-radius: 18px; }
  .file-detail-dialog :deep(.el-dialog__header) { padding: 18px 18px 14px; margin-right: 0; }.file-detail-dialog :deep(.el-dialog__body) { max-height: calc(100dvh - 158px); padding: 0 16px; }.file-detail-dialog :deep(.el-dialog__footer) { padding: 12px 16px calc(12px + env(safe-area-inset-bottom)); }.file-descriptions :deep(.el-descriptions__table) { font-size: 12px; }.file-descriptions :deep(.el-descriptions__cell) { padding: 9px 10px; }.detail-summary { padding: 13px; }.detail-cover { width: 48px; height: 48px; flex-basis: 48px; }
}
</style>
