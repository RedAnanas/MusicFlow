<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '../stores/app'
import TablePagination from '../components/TablePagination.vue'
import type { Task } from '../types'

const store = useAppStore()
const activeTab = ref('all')
const currentPage = ref(1)
const pageSize = ref(20)
const selectedTasks = ref<Task[]>([])
const actionLoading = ref(false)
const profilesLoaded = ref(false)
const selectedTask = ref<Task | null>(null)
const coverErrors = ref(new Set<string>())
const taskApiBase = 'http://localhost:8082/api/tasks'
let refreshTimer: ReturnType<typeof setInterval> | null = null

const statusFilters = [
  { label: '全部', value: 'all' },
  { label: '等待', value: 'waiting' },
  { label: '转换中', value: 'converting' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
]

onMounted(() => {
  store.fetchTasks()
  store.fetchFiles()
  refreshTimer = setInterval(() => store.fetchTasks(), 5000)
  store.fetchProfiles().finally(() => {
    profilesLoaded.value = true
  })
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

const filteredTasks = computed(() => {
  if (activeTab.value === 'all') {
    return store.tasks
  }
  return store.tasks.filter(task => task.status === activeTab.value)
})

const paginatedTasks = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredTasks.value.slice(start, start + pageSize.value)
})

const statusCounts = computed(() => ({
  converting: store.tasks.filter(task => task.status === 'converting').length,
  waiting: store.tasks.filter(task => task.status === 'waiting').length,
  success: store.tasks.filter(task => task.status === 'success').length,
  failed: store.tasks.filter(task => task.status === 'failed').length,
}))
const currentTask = computed(() => store.tasks.find(task => task.status === 'converting') || store.tasks.find(task => task.status === 'waiting') || null)
const inspectedTask = computed(() => selectedTask.value || currentTask.value || store.tasks[0] || null)
const getFileForTask = (task?: Task | null) => task ? store.files.find(file => file.path.replace(/\\/g, '/') === task.source_file?.replace(/\\/g, '/')) : undefined
const getCoverUrl = (task?: Task | null) => {
  const file = getFileForTask(task)
  return file ? `/api/files/${file.id}/cover` : ''
}
const markCoverError = (taskId: string) => { coverErrors.value.add(taskId); coverErrors.value = new Set(coverErrors.value) }
const fileName = (path?: string) => path?.split('/').pop() || '--'
const taskArtist = (task?: Task | null) => getFileForTask(task)?.artist || '未知艺术家'
const taskAlbum = (task?: Task | null) => getFileForTask(task)?.album || '未知专辑'

watch(activeTab, () => {
  currentPage.value = 1
  selectedTasks.value = []
})

watch(currentPage, () => {
  selectedTasks.value = []
})

watch(() => filteredTasks.value.length, (total) => {
  const lastPage = Math.max(1, Math.ceil(total / pageSize.value))
  if (currentPage.value > lastPage) {
    currentPage.value = lastPage
  }
})

const handleSizeChange = () => {
  currentPage.value = 1
  selectedTasks.value = []
}

const handleSelectionChange = (selection: Task[]) => {
  selectedTasks.value = selection
}

const getProfileName = (profileId?: string) => {
  if (!profileId) return '--'
  const profile = store.profiles.find(item => item.id === profileId)
  if (profile) return profile.name
  return profilesLoaded.value ? '已删除' : '--'
}

const ensureRequestSucceeded = async (response: Response) => {
  if (response.ok) return
  const result = await response.json().catch(() => null)
  throw new Error(result?.detail || `请求失败（HTTP ${response.status}）`)
}

const getErrorMessage = (error: unknown, fallback: string) => {
  return error instanceof Error ? error.message : fallback
}

const isConfirmationCancelled = (error: unknown) => {
  return error === 'cancel' || error === 'close'
}

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    waiting: 'info',
    converting: '',
    success: 'success',
    failed: 'danger',
    cancelled: 'warning',
    skipped: 'info',
  }
  return types[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    waiting: '等待',
    converting: '转换中',
    success: '成功',
    failed: '失败',
    cancelled: '已取消',
    skipped: '已跳过',
  }
  return labels[status] || status
}

const getAppleMusicStatusType = (status?: string) => {
  const types: Record<string, string> = {
    waiting: 'warning',
    received: 'success',
    failed: 'danger',
  }
  return status ? types[status] || 'info' : 'info'
}

const getAppleMusicStatusLabel = (status?: string) => {
  const labels: Record<string, string> = {
    waiting: '等待接收',
    received: '已接收',
    failed: '交接失败',
  }
  return status ? labels[status] || status : '--'
}

const formatDateTime = (time?: string) => {
  if (!time) return '--'
  const date = new Date(time)
  if (Number.isNaN(date.getTime())) return '--'
  const pad = (value: number) => String(value).padStart(2, '0')
  return [
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`,
  ].join(' ')
}

const handleCancel = async (taskId: string) => {
  try {
    const response = await fetch(`${taskApiBase}/${taskId}/cancel`, {
      method: 'POST'
    })
    await ensureRequestSucceeded(response)
    ElMessage.success('任务已取消')
    await store.fetchTasks()
  } catch (error) {
    console.error('Cancel failed:', error)
    ElMessage.error(getErrorMessage(error, '取消任务失败'))
  }
}

const handleRetry = async (taskId: string) => {
  try {
    const response = await fetch(`${taskApiBase}/${taskId}/retry`, {
      method: 'POST'
    })
    await ensureRequestSucceeded(response)
    ElMessage.success('重试任务已提交')
    await store.fetchTasks()
  } catch (error) {
    console.error('Retry failed:', error)
    ElMessage.error(getErrorMessage(error, '重试任务失败'))
  }
}

const handleDelete = async (task: Task) => {
  const isActive = task.status === 'waiting' || task.status === 'converting'
  const message = isActive
    ? '删除记录不会停止正在执行或排队的转换，确定继续吗？'
    : '确定删除这条任务记录吗？删除后无法恢复。'

  try {
    await ElMessageBox.confirm(message, '删除任务记录', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    const response = await fetch(`${taskApiBase}/${task.id}`, {
      method: 'DELETE',
    })
    await ensureRequestSucceeded(response)
    ElMessage.success('任务记录已删除')
    await store.fetchTasks()
  } catch (error) {
    if (isConfirmationCancelled(error)) return
    console.error('Delete failed:', error)
    ElMessage.error(getErrorMessage(error, '删除任务记录失败'))
  }
}

const handleBatchDelete = async () => {
  if (!selectedTasks.value.length) return

  const includesActiveTask = selectedTasks.value.some(task =>
    task.status === 'waiting' || task.status === 'converting'
  )
  const message = includesActiveTask
    ? `已选择 ${selectedTasks.value.length} 条记录，其中包含执行中或排队任务；删除记录不会停止转换，确定继续吗？`
    : `确定删除选中的 ${selectedTasks.value.length} 条任务记录吗？删除后无法恢复。`

  try {
    await ElMessageBox.confirm(message, '批量删除任务记录', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    actionLoading.value = true
    const response = await fetch(`${taskApiBase}/batch-delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_ids: selectedTasks.value.map(task => task.id) }),
    })
    await ensureRequestSucceeded(response)
    ElMessage.success(`已删除 ${selectedTasks.value.length} 条任务记录`)
    selectedTasks.value = []
    await store.fetchTasks()
  } catch (error) {
    if (isConfirmationCancelled(error)) return
    console.error('Batch delete failed:', error)
    ElMessage.error(getErrorMessage(error, '批量删除任务记录失败'))
  } finally {
    actionLoading.value = false
  }
}

const handleBatchRetry = async () => {
  if (!selectedTasks.value.length) return

  actionLoading.value = true
  try {
    const response = await fetch(`${taskApiBase}/batch-retry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_ids: selectedTasks.value.map(task => task.id) }),
    })
    await ensureRequestSucceeded(response)
    ElMessage.success(`已提交 ${selectedTasks.value.length} 个重试任务`)
    selectedTasks.value = []
    await store.fetchTasks()
  } catch (error) {
    console.error('Batch retry failed:', error)
    ElMessage.error(getErrorMessage(error, '批量重试失败'))
  } finally {
    actionLoading.value = false
  }
}
</script>

<template>
  <div class="tasks-page product-page">
    <div class="page-header">
      <div class="page-title-block">
        <h1>转换任务</h1>
        <p>查看队列进度、处理失败任务并追踪 Apple Music 交接状态。</p>
      </div>
      <div class="task-summary"><span><b>{{ filteredTasks.length }}</b> 条记录</span><span class="live-indicator">每 5 秒更新</span></div>
    </div>

    <section class="status-overview">
      <div><el-icon><Loading /></el-icon><span>转换中<strong>{{ statusCounts.converting }}</strong><small>正在执行</small></span></div>
      <div><el-icon><Clock /></el-icon><span>等待中<strong>{{ statusCounts.waiting }}</strong><small>队列中的任务</small></span></div>
      <div><el-icon><CircleCheck /></el-icon><span>已完成<strong>{{ statusCounts.success }}</strong><small>历史成功任务</small></span></div>
      <div><el-icon><Warning /></el-icon><span>失败<strong>{{ statusCounts.failed }}</strong><small>需要处理</small></span></div>
    </section>

    <section v-if="currentTask" class="current-task-card">
      <div class="task-cover">
        <img v-if="getCoverUrl(currentTask) && !coverErrors.has(currentTask.id)" :src="getCoverUrl(currentTask)" :alt="`${fileName(currentTask.source_file)} 封面`" @error="markCoverError(currentTask.id)" />
        <el-icon v-else><Headset /></el-icon>
      </div>
      <div class="current-task-copy"><span>当前正在转换</span><h2>{{ fileName(currentTask.source_file) }}</h2><p>{{ taskArtist(currentTask) }} · {{ taskAlbum(currentTask) }}</p><small>{{ currentTask.source_file }}</small></div>
      <div class="current-progress"><strong>{{ currentTask.progress || 0 }}%</strong><el-progress :percentage="currentTask.progress || 0" :show-text="false" :stroke-width="8" /><span>{{ getProfileName(currentTask.profile_id) }} · {{ currentTask.status === 'converting' ? '正在处理' : '等待开始' }}</span></div>
    </section>

    <div class="task-workspace">
      <el-card class="task-list-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane
          v-for="filter in statusFilters"
          :key="filter.value"
          :label="filter.label"
          :name="filter.value"
        />
      </el-tabs>

      <div class="task-toolbar">
        <el-button
          type="danger"
          :disabled="selectedTasks.length === 0"
          :loading="actionLoading"
          @click="handleBatchDelete"
        >
          批量删除
        </el-button>
        <el-button
          v-if="activeTab === 'failed'"
          type="warning"
          :disabled="selectedTasks.length === 0"
          :loading="actionLoading"
          @click="handleBatchRetry"
        >
          批量重试
        </el-button>
        <span v-if="selectedTasks.length" class="selection-count">
          已选择 {{ selectedTasks.length }} 条
        </span>
      </div>

      <el-table
        :data="paginatedTasks"
        style="width: 100%"
        v-loading="store.loading"
        @selection-change="handleSelectionChange"
        @row-click="selectedTask = $event"
      >
        <el-table-column type="selection" width="50" />

        <el-table-column prop="source_file" label="文件信息" min-width="220">
          <template #default="{ row }">
            <div class="task-file-cell">
              <span class="task-cover small"><img v-if="getCoverUrl(row) && !coverErrors.has(row.id)" :src="getCoverUrl(row)" :alt="`${fileName(row.source_file)} 封面`" loading="lazy" @error="markCoverError(row.id)" /><el-icon v-else><Headset /></el-icon></span>
              <span><strong>{{ fileName(row.source_file) }}</strong><small>{{ taskArtist(row) }} · {{ taskAlbum(row) }}</small></span>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="output_file" label="输出文件" min-width="170">
          <template #default="{ row }">
            {{ row.output_file?.split('/').pop() }}
          </template>
        </el-table-column>

        <el-table-column label="转换配置" width="100">
          <template #default="{ row }">
            {{ getProfileName(row.profile_id) }}
          </template>
        </el-table-column>

        <el-table-column prop="status" label="状态" width="78">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="Apple Music" width="100">
          <template #default="{ row }">
            <el-tooltip v-if="row.apple_music_error" :content="row.apple_music_error" placement="top">
              <el-tag :type="getAppleMusicStatusType(row.apple_music_status)" size="small">
                {{ getAppleMusicStatusLabel(row.apple_music_status) }}
              </el-tag>
            </el-tooltip>
            <el-tag v-else :type="getAppleMusicStatusType(row.apple_music_status)" size="small">
              {{ getAppleMusicStatusLabel(row.apple_music_status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="进度" width="104">
          <template #default="{ row }">
            <el-progress
              v-if="row.status === 'converting'"
              :percentage="row.progress || 0"
              :status="row.progress === 100 ? 'success' : ''"
            />
            <span v-else-if="row.status === 'success'">100%</span>
            <span v-else>--</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="82" fixed="right">
          <template #default="{ row }">
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
            <el-button
              type="danger"
              link
              size="small"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <TablePagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="filteredTasks.length"
        @size-change="handleSizeChange"
      />
      </el-card>

      <aside class="task-inspector">
        <template v-if="inspectedTask">
          <div class="inspector-top"><span>任务详情</span><el-tag :type="getStatusType(inspectedTask.status)" size="small">{{ getStatusLabel(inspectedTask.status) }}</el-tag></div>
          <div class="inspector-track"><span class="task-cover"><img v-if="getCoverUrl(inspectedTask) && !coverErrors.has(inspectedTask.id)" :src="getCoverUrl(inspectedTask)" :alt="`${fileName(inspectedTask.source_file)} 封面`" @error="markCoverError(inspectedTask.id)" /><el-icon v-else><Headset /></el-icon></span><div><strong>{{ fileName(inspectedTask.source_file) }}</strong><small>{{ taskArtist(inspectedTask) }} · {{ taskAlbum(inspectedTask) }}</small></div></div>
          <dl class="task-facts"><div><dt>转换方案</dt><dd>{{ getProfileName(inspectedTask.profile_id) }}</dd></div><div><dt>创建时间</dt><dd>{{ formatDateTime(inspectedTask.start_time) }}</dd></div><div><dt>Apple Music</dt><dd>{{ getAppleMusicStatusLabel(inspectedTask.apple_music_status) }}</dd></div></dl>
          <h3>处理流程</h3>
          <ol class="pipeline"><li class="done">读取元数据<span>完成</span></li><li :class="{ done: inspectedTask.status === 'success', active: inspectedTask.status === 'converting' }">音频转码<span>{{ inspectedTask.status === 'converting' ? `${inspectedTask.progress || 0}%` : inspectedTask.status === 'success' ? '完成' : '等待' }}</span></li><li :class="{ done: inspectedTask.status === 'success' }">写入封面<span>{{ inspectedTask.status === 'success' ? '完成' : '等待' }}</span></li><li :class="{ done: inspectedTask.apple_music_status === 'received' }">Apple Music 交接<span>{{ getAppleMusicStatusLabel(inspectedTask.apple_music_status) }}</span></li></ol>
          <div v-if="inspectedTask.error" class="task-error"><strong>失败原因</strong><span>{{ inspectedTask.error }}</span></div>
          <div class="inspector-buttons"><el-button v-if="inspectedTask.status === 'failed'" type="primary" @click="handleRetry(inspectedTask.id)">重试任务</el-button><el-button v-if="['waiting','converting'].includes(inspectedTask.status)" plain @click="handleCancel(inspectedTask.id)">取消任务</el-button></div>
        </template>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.tasks-page {
  padding-bottom: 32px;
}

.task-summary {
  display: flex;
  gap: 16px;
  align-items: center;
  color: #748179;
  font-size: 13px;
}

.task-summary b {
  color: #0c9c68;
  font-size: 20px;
}

.live-indicator::before {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 6px;
  border-radius: 50%;
  background: #19af77;
  content: '';
}

.status-overview { display: grid; grid-template-columns: repeat(4, 1fr); margin-bottom: 18px; border: 1px solid var(--mf-line); border-radius: 12px; background: var(--mf-surface); }
.status-overview > div { display: flex; gap: 12px; align-items: center; min-height: 82px; padding: 16px 20px; border-right: 1px solid #e5e9e5; }.status-overview > div:last-child { border-right: 0; }
.status-overview > div > .el-icon { color: #0c9c68; font-size: 23px; }.status-overview > div:last-child > .el-icon { color: #dc5b56; }
.status-overview span { display: grid; grid-template-columns: auto 1fr; gap: 2px 8px; align-items: baseline; color: #607068; font-size: 12px; }.status-overview strong { color: #203028; font-size: 22px; }.status-overview small { grid-column: 1 / -1; color: #8a968f; }
.current-task-card { display: grid; grid-template-columns: 74px minmax(240px, 1fr) minmax(260px, .8fr); gap: 18px; align-items: center; margin-bottom: 18px; padding: 16px; border: 1px solid var(--mf-line); border-radius: 12px; background: var(--mf-surface); }
.task-cover { display: grid; width: 74px; height: 74px; flex: 0 0 auto; place-items: center; overflow: hidden; border-radius: 8px; background: #e5f1eb; color: #148b61; font-size: 28px; }.task-cover img { width: 100%; height: 100%; object-fit: cover; }.task-cover.small { width: 38px; height: 38px; border-radius: 5px; font-size: 16px; }
.current-task-copy { min-width: 0; }.current-task-copy > span { color: #168d63; font-size: 12px; }.current-task-copy h2 { margin: 3px 0; overflow: hidden; color: #24322b; font-size: 17px; text-overflow: ellipsis; white-space: nowrap; }.current-task-copy p, .current-task-copy small { display: block; overflow: hidden; color: #7d8982; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.current-progress { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; }.current-progress strong { color: #0c9c68; font-size: 24px; }.current-progress .el-progress { grid-column: 1 / -1; }.current-progress span { grid-column: 1 / -1; color: #839087; font-size: 12px; }
.task-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 250px; align-items: start; border: 1px solid var(--mf-line); border-radius: 12px; background: var(--mf-surface); overflow: hidden; }
.task-list-card { border: 0 !important; border-radius: 0 !important; box-shadow: none !important; }.task-list-card > :deep(.el-card__body) { padding: 0; }
.task-file-cell { display: flex; gap: 10px; align-items: center; }.task-file-cell > span:last-child { display: flex; min-width: 0; flex-direction: column; gap: 2px; }.task-file-cell strong, .task-file-cell small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.task-file-cell strong { color: #314038; font-size: 13px; }.task-file-cell small { color: #8a968f; font-size: 11px; }
.task-inspector { min-height: 620px; padding: 18px; border-left: 1px solid #e2e7e3; }.inspector-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; color: #304039; font-size: 13px; font-weight: 600; }.inspector-track { display: flex; gap: 12px; align-items: center; }.inspector-track .task-cover { width: 58px; height: 58px; }.inspector-track > div { display: flex; min-width: 0; flex-direction: column; gap: 4px; }.inspector-track strong, .inspector-track small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.inspector-track strong { color: #26352d; font-size: 13px; }.inspector-track small { color: #849088; font-size: 11px; }
.task-facts { margin: 18px 0; padding: 12px 0; border-top: 1px solid #e4e9e5; border-bottom: 1px solid #e4e9e5; }.task-facts div { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; font-size: 11px; }.task-facts dt { color: #89958e; }.task-facts dd { max-width: 150px; overflow: hidden; color: #435149; text-overflow: ellipsis; white-space: nowrap; }
.task-inspector h3 { margin: 0 0 12px; color: #314038; font-size: 13px; }.pipeline { margin: 0; padding: 0; list-style: none; }.pipeline li { position: relative; display: flex; justify-content: space-between; margin-left: 6px; padding: 0 0 18px 18px; border-left: 1px solid #d9dfda; color: #7e8b83; font-size: 11px; }.pipeline li::before { position: absolute; top: 1px; left: -5px; width: 9px; height: 9px; border-radius: 50%; background: #cbd3cd; content: ''; }.pipeline li.done::before, .pipeline li.active::before { background: #0c9c68; }.pipeline li.done { color: #405047; }.pipeline li.active { color: #0c8e61; font-weight: 600; }.pipeline li:last-child { border-left-color: transparent; }
.task-error { display: flex; flex-direction: column; gap: 5px; padding: 10px; border-radius: 7px; background: #fff2f1; color: #b64b47; font-size: 11px; line-height: 1.5; }.inspector-buttons { display: flex; gap: 8px; margin-top: 16px; }.inspector-buttons .el-button { flex: 1; margin: 0; }

.task-toolbar {
  display: flex;
  align-items: center;
  min-height: 56px;
  padding: 0 20px;
  border-bottom: 1px solid #e4e9e5;
}

.selection-count {
  margin-left: 12px;
  color: #606266;
  font-size: 14px;
}

:deep(.el-tabs__header) {
  margin: 0;
  padding: 0 20px;
}

:deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: #e4e9e5;
}

:deep(.el-tabs__item) {
  height: 54px;
  color: #66736b;
}

:deep(.el-tabs__item.is-active) {
  color: #0c9c68;
  font-weight: 600;
}

:deep(.el-tabs__active-bar) {
  background: #0c9c68;
}

:deep(.el-table .el-scrollbar__bar.is-vertical) {
  display: none;
}

:deep(.el-table .el-scrollbar__wrap) {
  overflow-y: hidden;
}

@media (max-width: 1180px) { .task-workspace { grid-template-columns: 1fr; }.task-inspector { display: none; } }
@media (max-width: 800px) { .status-overview { grid-template-columns: repeat(2, 1fr); }.status-overview > div:nth-child(2) { border-right: 0; }.status-overview > div:nth-child(-n+2) { border-bottom: 1px solid #e5e9e5; }.current-task-card { grid-template-columns: 58px 1fr; }.current-task-card .task-cover { width: 58px; height: 58px; }.current-progress { grid-column: 1 / -1; } }
</style>
