<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const levelFilter = ref('')
const limit = ref(100)

onMounted(() => {
  store.fetchLogs(limit.value)
})

const getLevelType = (level: string) => {
  const types: Record<string, string> = {
    INFO: 'success',
    WARNING: 'warning',
    ERROR: 'danger',
    DEBUG: 'info',
  }
  return types[level] || 'info'
}

const formatTimestamp = (timestamp: string) => {
  return new Date(timestamp).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="logs-page product-page">
    <div class="page-header">
      <div class="page-title-block">
        <h1>日志</h1>
        <p>查看系统运行记录，快速定位扫描、转换和交接异常。</p>
      </div>
      <div class="header-actions">
        <el-select v-model="levelFilter" placeholder="日志级别" clearable style="width: 120px; margin-right: 10px">
          <el-option label="INFO" value="INFO" />
          <el-option label="WARNING" value="WARNING" />
          <el-option label="ERROR" value="ERROR" />
          <el-option label="DEBUG" value="DEBUG" />
        </el-select>
        <el-input-number v-model="limit" :min="10" :max="1000" :step="10" style="width: 120px; margin-right: 10px" />
        <el-button type="primary" @click="store.fetchLogs(limit)">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 日志列表 -->
    <el-card v-loading="store.loading">
      <el-table :data="store.logs" style="width: 100%">
        <el-table-column prop="timestamp" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTimestamp(row.timestamp) }}
          </template>
        </el-table-column>

        <el-table-column prop="level" label="级别" width="100">
          <template #default="{ row }">
            <el-tag :type="getLevelType(row.level)" size="small">
              {{ row.level }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="module" label="模块" width="150" />

        <el-table-column prop="message" label="消息" min-width="300" />

        <el-table-column prop="details" label="详情" min-width="200">
          <template #default="{ row }">
            <span v-if="row.details" class="details-text">{{ row.details }}</span>
            <span v-else>--</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.logs-page {
  padding-bottom: 32px;
}

.header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.header-actions :deep(.el-select),
.header-actions :deep(.el-input-number) {
  margin-right: 0 !important;
}

.details-text {
  color: #909399;
  font-size: 12px;
}

:deep(.el-card__body) {
  overflow: hidden;
  border-radius: 12px;
}

@media (max-width: 820px) {
  .header-actions {
    flex-wrap: wrap;
  }
}
</style>
