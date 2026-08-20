<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '../stores/app'
import type { LogEntry } from '../types'

const store = useAppStore()
const searchQuery = ref('')
const levelFilter = ref('')
const moduleFilter = ref('')
const limit = ref(200)
const autoRefresh = ref(true)
const selectedLog = ref<LogEntry | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | undefined

const filteredLogs = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return store.logs.filter(log => {
    const matchesLevel = !levelFilter.value || log.level === levelFilter.value
    const matchesModule = !moduleFilter.value || log.module === moduleFilter.value
    const matchesQuery = !query || [log.message, log.details, log.module].some(value => value?.toLowerCase().includes(query))
    return matchesLevel && matchesModule && matchesQuery
  })
})

const modules = computed(() => [...new Set(store.logs.map(log => log.module))].sort())
const levelCounts = computed(() => ({ ALL: store.logs.length, ERROR: store.logs.filter(log => log.level === 'ERROR').length, WARNING: store.logs.filter(log => log.level === 'WARNING').length, INFO: store.logs.filter(log => log.level === 'INFO').length, DEBUG: store.logs.filter(log => log.level === 'DEBUG').length }))

onMounted(async () => {
  await store.fetchLogs(limit.value)
  selectedLog.value = store.logs[0] || null
  refreshTimer = setInterval(() => { if (autoRefresh.value) store.fetchLogs(limit.value) }, 5000)
})
onUnmounted(() => { if (refreshTimer) clearInterval(refreshTimer) })
watch(filteredLogs, logs => {
  if (!logs.length) selectedLog.value = null
  else if (!selectedLog.value || !logs.includes(selectedLog.value)) selectedLog.value = logs[0]
})

const getLevelType = (level: string) => ({ INFO: 'success', WARNING: 'warning', ERROR: 'danger', DEBUG: 'info' }[level] || 'info')
const formatTimestamp = (timestamp: string) => new Date(timestamp).toLocaleString('zh-CN', { hour12: false })
const copyDetails = async () => {
  if (!selectedLog.value) return
  const log = selectedLog.value
  const text = [`时间：${formatTimestamp(log.timestamp)}`, `级别：${log.level}`, `模块：${log.module}`, `消息：${log.message}`, log.details ? `详情：${log.details}` : ''].filter(Boolean).join('\n')
  await navigator.clipboard.writeText(text)
  ElMessage.success('日志详情已复制')
}
</script>

<template>
  <div class="logs-page product-page">
    <div class="page-header">
      <div class="page-title-block"><h1>日志</h1><p>查看系统运行记录，快速定位扫描、转换和交接异常。</p></div>
      <div class="header-actions"><span>自动刷新</span><el-switch v-model="autoRefresh" /><el-button type="primary" @click="store.fetchLogs(limit)"><el-icon><Refresh /></el-icon>刷新</el-button></div>
    </div>
    <div class="log-toolbar">
      <el-input v-model="searchQuery" clearable placeholder="搜索消息、详情或模块"><template #prefix><el-icon><Search /></el-icon></template></el-input>
      <el-select v-model="levelFilter" placeholder="全部级别" clearable><el-option label="错误" value="ERROR" /><el-option label="警告" value="WARNING" /><el-option label="信息" value="INFO" /><el-option label="调试" value="DEBUG" /></el-select>
      <el-select v-model="moduleFilter" placeholder="全部模块" clearable><el-option v-for="module in modules" :key="module" :label="module" :value="module" /></el-select>
      <el-select v-model="limit" @change="store.fetchLogs(limit)"><el-option label="最近 100 条" :value="100" /><el-option label="最近 200 条" :value="200" /><el-option label="最近 500 条" :value="500" /><el-option label="最近 1000 条" :value="1000" /></el-select>
    </div>
    <div class="level-summary">
      <button v-for="item in [{ key: '', label: '全部', count: levelCounts.ALL }, { key: 'ERROR', label: '错误', count: levelCounts.ERROR }, { key: 'WARNING', label: '警告', count: levelCounts.WARNING }, { key: 'INFO', label: '信息', count: levelCounts.INFO }, { key: 'DEBUG', label: '调试', count: levelCounts.DEBUG }]" :key="item.label" type="button" :class="[item.key.toLowerCase(), { active: levelFilter === item.key }]" @click="levelFilter = item.key"><span>{{ item.label }}</span><strong>{{ item.count }}</strong></button>
    </div>
    <div class="logs-workspace" v-loading="store.loading">
      <section class="log-table-panel">
        <div class="table-caption"><strong>系统日志</strong><span>显示 {{ filteredLogs.length }} / {{ store.logs.length }} 条记录</span></div>
        <el-table :data="filteredLogs" highlight-current-row height="548" @current-change="(row: LogEntry) => selectedLog = row">
          <el-table-column label="时间" width="168"><template #default="{ row }"><span class="time-cell">{{ formatTimestamp(row.timestamp) }}</span></template></el-table-column>
          <el-table-column label="级别" width="90"><template #default="{ row }"><el-tag :type="getLevelType(row.level)" effect="light" size="small">{{ row.level }}</el-tag></template></el-table-column>
          <el-table-column prop="module" label="模块" width="130"><template #default="{ row }"><code class="module-cell">{{ row.module }}</code></template></el-table-column>
          <el-table-column prop="message" label="消息" min-width="300" show-overflow-tooltip />
        </el-table>
      </section>
      <aside v-if="selectedLog" class="log-inspector">
        <div class="inspector-heading"><div><span class="eyebrow">诊断详情</span><h2>{{ selectedLog.module }}</h2></div><el-tag :type="getLevelType(selectedLog.level)">{{ selectedLog.level }}</el-tag></div>
        <div class="diagnostic-banner" :class="selectedLog.level.toLowerCase()"><el-icon><CircleCloseFilled v-if="selectedLog.level === 'ERROR'" /><WarningFilled v-else-if="selectedLog.level === 'WARNING'" /><InfoFilled v-else /></el-icon><div><strong>{{ selectedLog.message }}</strong><span>{{ formatTimestamp(selectedLog.timestamp) }}</span></div></div>
        <section><h3>上下文</h3><dl><div><dt>记录时间</dt><dd>{{ formatTimestamp(selectedLog.timestamp) }}</dd></div><div><dt>来源模块</dt><dd><code>{{ selectedLog.module }}</code></dd></div><div><dt>日志级别</dt><dd>{{ selectedLog.level }}</dd></div></dl></section>
        <section class="detail-section"><h3>详细信息</h3><pre>{{ selectedLog.details || '此条日志没有附加详情。' }}</pre></section>
        <div class="diagnostic-tip"><el-icon><QuestionFilled /></el-icon><span>{{ selectedLog.level === 'ERROR' ? '建议先检查相关目录与服务状态，再根据详情定位失败步骤。' : '此记录用于说明系统运行过程，可复制后用于问题反馈。' }}</span></div>
        <el-button class="copy-button" type="primary" plain @click="copyDetails"><el-icon><CopyDocument /></el-icon>复制诊断信息</el-button>
      </aside>
      <aside v-else class="log-inspector empty-inspector"><el-empty description="选择一条日志查看详情" :image-size="70" /></aside>
    </div>
  </div>
</template>

<style scoped>
.logs-page { padding-bottom: 32px; }
.header-actions { display: flex; align-items: center; gap: 10px; color: #7f8a86; font-size: 12px; }
.log-toolbar { display: grid; grid-template-columns: minmax(260px, 1fr) 140px 160px 150px; gap: 10px; padding: 14px; margin-bottom: 12px; background: #fff; border: 1px solid #e7ece9; border-radius: 14px; }
.level-summary { display: grid; grid-template-columns: repeat(5, 1fr); margin-bottom: 14px; overflow: hidden; background: #fff; border: 1px solid #e7ece9; border-radius: 14px; }
.level-summary button { display: flex; align-items: center; justify-content: space-between; padding: 14px 19px; color: #77837e; background: transparent; border: 0; border-right: 1px solid #edf0ef; cursor: pointer; }
.level-summary button:last-child { border-right: 0; }
.level-summary button:hover, .level-summary button.active { background: #f2f8f5; }
.level-summary button strong { color: #32403a; font-size: 20px; }
.level-summary .error strong { color: #dc514b; }.level-summary .warning strong { color: #d8952a; }.level-summary .info strong { color: #0c9c68; }
.logs-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 370px; min-height: 620px; overflow: hidden; background: #fff; border: 1px solid #e7ece9; border-radius: 16px; box-shadow: 0 12px 36px rgba(18, 58, 45, .05); }
.log-table-panel { min-width: 0; border-right: 1px solid #e7ece9; }
.table-caption { display: flex; align-items: center; justify-content: space-between; padding: 18px 20px; border-bottom: 1px solid #edf0ef; }.table-caption strong { color: #293630; font-size: 15px; }.table-caption span { color: #98a19e; font-size: 11px; }
.time-cell { color: #68746f; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; }.module-cell { color: #3d6255; font-size: 10px; }
.log-inspector { min-width: 0; padding: 24px; background: #fbfcfc; }.empty-inspector { display: grid; place-items: center; }
.inspector-heading { display: flex; align-items: flex-start; justify-content: space-between; padding-bottom: 18px; border-bottom: 1px solid #e6ebe8; }.eyebrow { display: block; margin-bottom: 5px; color: #0c9c68; font-size: 10px; font-weight: 800; letter-spacing: .12em; }.inspector-heading h2 { margin: 0; color: #26332e; font-size: 20px; }
.diagnostic-banner { display: flex; align-items: flex-start; gap: 11px; padding: 14px; margin: 18px 0; color: #247155; background: #eaf7f2; border: 1px solid #cceade; border-radius: 11px; }.diagnostic-banner.error { color: #ca4944; background: #fff0ef; border-color: #f1d0cd; }.diagnostic-banner.warning { color: #b77719; background: #fff7e8; border-color: #f1dfbb; }.diagnostic-banner > .el-icon { flex: 0 0 auto; margin-top: 2px; font-size: 18px; }.diagnostic-banner > div { display: flex; min-width: 0; flex-direction: column; gap: 6px; }.diagnostic-banner strong { color: #34413c; font-size: 12px; line-height: 1.5; }.diagnostic-banner span { color: #8a9590; font-size: 10px; }
.log-inspector section { padding: 15px 0; border-top: 1px solid #e6ebe8; }.log-inspector section h3 { margin: 0 0 12px; color: #55625d; font-size: 11px; }.log-inspector dl { margin: 0; }.log-inspector dl > div { display: flex; justify-content: space-between; gap: 12px; min-height: 29px; }.log-inspector dt { color: #98a19d; font-size: 10px; }.log-inspector dd { margin: 0; color: #3b4843; font-size: 11px; font-weight: 600; }
.detail-section pre { max-height: 180px; padding: 13px; overflow: auto; color: #53605b; white-space: pre-wrap; word-break: break-word; background: #f0f4f2; border-radius: 8px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; line-height: 1.6; }.diagnostic-tip { display: flex; gap: 9px; padding: 12px; color: #71807a; background: #f1f5f3; border-radius: 9px; font-size: 10px; line-height: 1.5; }.diagnostic-tip .el-icon { flex: 0 0 auto; margin-top: 2px; color: #0c9c68; }.copy-button { width: 100%; margin-top: 14px; }
@media (max-width: 900px) { .log-toolbar { grid-template-columns: 1fr 1fr; } .logs-workspace { grid-template-columns: 1fr; } .log-table-panel { border-right: 0; border-bottom: 1px solid #e7ece9; } }
@media (max-width: 600px) { .level-summary { grid-template-columns: 1fr; } .level-summary button { border-right: 0; border-bottom: 1px solid #edf0ef; } }
</style>
