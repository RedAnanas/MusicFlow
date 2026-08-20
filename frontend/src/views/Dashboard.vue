<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()

const stats = ref({
  watchFolders: 0,
  pending: 0,
  converting: 0,
  completed: 0,
  failed: 0,
  todayConverted: 0,
})

const currentTask = ref<{
  filename: string
  progress: number
  codec: string
  bitrate: string
  eta: string
} | null>(null)

onMounted(async () => {
  await Promise.all([
    store.fetchFiles(),
    store.fetchTasks(),
    store.fetchWatchFolders(),
  ])

  // 计算统计数据
  stats.value.watchFolders = store.watchFolders.length
  stats.value.pending = store.tasks.filter(task => task.status === 'waiting').length
  stats.value.converting = store.tasks.filter(task => task.status === 'converting').length
  stats.value.completed = store.tasks.filter(task => task.status === 'success').length
  stats.value.failed = store.tasks.filter(task => task.status === 'failed').length

  // 获取当前转换任务
  const activeTask = store.tasks.find(t => t.status === 'converting')
  if (activeTask) {
    currentTask.value = {
      filename: activeTask.sourceFile.split('/').pop() || '',
      progress: activeTask.progress || 0,
      codec: 'AAC',
      bitrate: '256kbps',
      eta: '12秒',
    }
  }
})
</script>

<template>
  <div class="dashboard">
    <h1>仪表盘</h1>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ stats.watchFolders }}</div>
          <div class="stat-label">监控目录</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card pending">
          <div class="stat-value">{{ stats.pending }}</div>
          <div class="stat-label">待处理</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card converting">
          <div class="stat-value">{{ stats.converting }}</div>
          <div class="stat-label">转换中</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card completed">
          <div class="stat-value">{{ stats.completed }}</div>
          <div class="stat-label">已完成</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card failed">
          <div class="stat-value">{{ stats.failed }}</div>
          <div class="stat-label">失败</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card today">
          <div class="stat-value">{{ stats.todayConverted }}</div>
          <div class="stat-label">今日转换</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 当前任务 -->
    <el-card v-if="currentTask" class="current-task-card">
      <template #header>
        <div class="card-header">
          <span>当前任务</span>
        </div>
      </template>

      <div class="current-task">
        <div class="task-info">
          <h3>{{ currentTask.filename }}</h3>
          <p>{{ currentTask.codec }} {{ currentTask.bitrate }}</p>
          <p>预计剩余 {{ currentTask.eta }}</p>
        </div>
        <el-progress
          :percentage="currentTask.progress"
          :status="currentTask.progress === 100 ? 'success' : ''"
          :stroke-width="20"
          class="task-progress"
        />
      </div>
    </el-card>

  </div>
</template>

<style scoped>
.dashboard {
  padding: 0;
}

h1 {
  margin-bottom: 20px;
  color: #303133;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #409eff;
  margin-bottom: 5px;
}

.stat-card.pending .stat-value {
  color: #e6a23c;
}

.stat-card.converting .stat-value {
  color: #409eff;
}

.stat-card.completed .stat-value {
  color: #67c23a;
}

.stat-card.failed .stat-value {
  color: #f56c6c;
}

.stat-card.today .stat-value {
  color: #909399;
}

.stat-label {
  font-size: 14px;
  color: #909399;
}

.current-task-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
}

.current-task {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.task-info h3 {
  margin-bottom: 5px;
  color: #303133;
}

.task-info p {
  color: #909399;
  font-size: 14px;
}

.task-progress {
  width: 100%;
}

</style>
