<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useAppStore } from '../stores/app'
import type { Task } from '../types'

const store = useAppStore()
const activeTab = ref('all')

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
})

const filteredTasks = computed(() => {
  if (activeTab.value === 'all') {
    return store.tasks
  }
  return store.tasks.filter(task => task.status === activeTab.value)
})

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

const formatDuration = (startTime?: string, endTime?: string) => {
  if (!startTime) return '--'
  const start = new Date(startTime).getTime()
  const end = endTime ? new Date(endTime).getTime() : Date.now()
  const duration = Math.floor((end - start) / 1000)
  const mins = Math.floor(duration / 60)
  const secs = duration % 60
  return `${mins}分${secs}秒`
}

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

      <el-table
        :data="filteredTasks"
        style="width: 100%"
        v-loading="store.loading"
      >
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

        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="进度" width="200">
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

        <el-table-column label="耗时" width="120">
          <template #default="{ row }">
            {{ formatDuration(row.start_time, row.end_time) }}
          </template>
        </el-table-column>

        <el-table-column prop="error" label="错误信息" min-width="200">
          <template #default="{ row }">
            <span v-if="row.error" class="error-text">{{ row.error }}</span>
            <span v-else>--</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="150" fixed="right">
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
          </template>
        </el-table-column>
      </el-table>
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

.error-text {
  color: #f56c6c;
  font-size: 12px;
}
</style>
