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

const formatDuration = (startTime?: string, endTime?: string) => {
  if (!startTime) return '--'
  const start = new Date(startTime).getTime()
  const end = endTime ? new Date(endTime).getTime() : Date.now()
  const duration = Math.floor((end - start) / 1000)
  const mins = Math.floor(duration / 60)
  const secs = duration % 60
  return `${mins}分${secs}秒`
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
  <div class="tasks-page">
    <h1>转换任务</h1>

    <!-- 任务列表 -->
    <el-card>
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
      >
        <el-table-column type="selection" width="50" />

        <el-table-column label="序号" width="60" align="center">
          <template #default="{ $index }">
            {{ (currentPage - 1) * pageSize + $index + 1 }}
          </template>
        </el-table-column>

        <el-table-column prop="source_file" label="源文件" min-width="200">
          <template #default="{ row }">
            {{ row.source_file?.split('/').pop() }}
          </template>
        </el-table-column>

        <el-table-column prop="output_file" label="输出文件" min-width="200">
          <template #default="{ row }">
            {{ row.output_file?.split('/').pop() }}
          </template>
        </el-table-column>

        <el-table-column label="转换配置" width="130">
          <template #default="{ row }">
            {{ getProfileName(row.profile_id) }}
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.start_time) }}
          </template>
        </el-table-column>

        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="Apple Music" width="120">
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

        <el-table-column label="进度" width="150">
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

        <el-table-column label="耗时" width="100">
          <template #default="{ row }">
            {{ formatDuration(row.start_time, row.end_time) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="130" fixed="right">
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
  </div>
</template>

<style scoped>
.tasks-page {
  padding: 0;
}

h1 {
  margin-bottom: 20px;
  color: #303133;
}

.task-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
}

.selection-count {
  margin-left: 12px;
  color: #606266;
  font-size: 14px;
}

:deep(.el-table .el-scrollbar__bar.is-vertical) {
  display: none;
}

:deep(.el-table .el-scrollbar__wrap) {
  overflow-y: hidden;
}
</style>
