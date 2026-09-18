<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '../stores/app'
import TablePagination from '../components/TablePagination.vue'

const store = useAppStore()
const route = useRoute()
const router = useRouter()
const view = ref(route.query.tab === 'logs' ? 'logs' : 'records')
const status = ref('all')
const level = ref('all')
const keyword = ref('')
const selectedIds = ref<string[]>([])
const page = ref(1)
const logPage = ref(1)
const taskPageSize = ref(100)
const logPageSize = ref(200)
const profilesLoaded = ref(false)
const actionLoading = ref(false)
let timer: ReturnType<typeof setInterval> | undefined

const fileName = (path?: string) => path?.replace(/\\/g, '/').split('/').pop() || '未命名文件'
const profileName = (id?: string) => store.profiles.find(item => item.id === id)?.name || (id && profilesLoaded.value ? '已删除方案' : '未指定方案')
const dateTime = (value?: string) => {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '--' : date.toLocaleString('zh-CN', { hour12: false })
}
const taskLabel = (value: string) => ({ waiting: '等待', converting: '转换中', success: '成功', failed: '失败', cancelled: '已取消', skipped: '已跳过' }[value] || value)
const taskType = (value: string) => ({ waiting: 'info', converting: 'warning', success: 'success', failed: 'danger', cancelled: 'info', skipped: 'info' }[value] || 'info')
const appleMusicLabel = (value?: string) => ({ waiting: '等待 Apple Music 接收', received: 'Apple Music 已接收', failed: 'Apple Music 交接失败' }[value || ''] || '')
const appleMusicType = (value?: string) => ({ waiting: 'warning', received: 'success', failed: 'danger' }[value || ''] || 'info')
const logType = (value: string) => ({ ERROR: 'danger', WARNING: 'warning', INFO: 'success', DEBUG: 'info' }[value] || 'info')
const filteredTasks = computed(() => store.tasks.filter(task => (status.value === 'all' || task.status === status.value) && (!keyword.value.trim() || `${fileName(task.source_file)} ${profileName(task.profile_id)}`.toLowerCase().includes(keyword.value.trim().toLowerCase()))))
const pageCount = computed(() => Math.max(1, Math.ceil(filteredTasks.value.length / taskPageSize.value)))
const tasks = computed(() => filteredTasks.value.slice((page.value - 1) * taskPageSize.value, page.value * taskPageSize.value))
const logs = computed(() => store.logs.filter(log => (level.value === 'all' || log.level === level.value) && (!keyword.value.trim() || `${log.module} ${log.message}`.toLowerCase().includes(keyword.value.trim().toLowerCase()))))
const logPageCount = computed(() => Math.max(1, Math.ceil(logs.value.length / logPageSize.value)))
const paginatedLogs = computed(() => logs.value.slice((logPage.value - 1) * logPageSize.value, logPage.value * logPageSize.value))
const counts = computed(() => ({ converting: store.tasks.filter(item => item.status === 'converting').length, waiting: store.tasks.filter(item => item.status === 'waiting').length, failed: store.tasks.filter(item => item.status === 'failed').length }))

onMounted(async () => {
  await Promise.all([store.fetchTasks(), store.fetchLogs(200), store.fetchProfiles().finally(() => { profilesLoaded.value = true })])
  timer = setInterval(() => { store.fetchTasks(); if (view.value === 'logs') store.fetchLogs(200) }, 5000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
watch(() => route.query.tab, tab => { view.value = tab === 'logs' ? 'logs' : 'records' })
watch([view, status, keyword], () => { page.value = 1; logPage.value = 1 })
watch(pageCount, total => { if (page.value > total) page.value = total })
watch(logPageCount, total => { if (logPage.value > total) logPage.value = total })
watch(view, next => { router.replace({ path: '/tasks', query: next === 'logs' ? { tab: 'logs' } : {} }); keyword.value = ''; if (next === 'logs') store.fetchLogs(200) })

const toggle = (id: string) => { selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(item => item !== id) : [...selectedIds.value, id] }
const request = async (url: string, init: RequestInit) => { const response = await fetch(url, init); if (response.ok) return; const body = await response.json().catch(() => null); throw new Error(body?.detail || `请求失败（HTTP ${response.status}）`) }
const retry = async (id: string) => { try { await request(`/api/tasks/${id}/retry`, { method: 'POST' }); ElMessage.success('重试任务已提交'); await store.fetchTasks() } catch (error) { ElMessage.error(error instanceof Error ? error.message : '重试任务失败') } }
const retryAppleMusic = async (id: string, received = false) => { try { if (received) await ElMessageBox.confirm('该记录已标记为 Apple Music 已接收，再次交接可能导致重复导入。确定继续吗？', '再次交接', { confirmButtonText: '继续交接', cancelButtonText: '取消', type: 'warning' }); await request(`/api/tasks/${id}/retry-apple-music`, { method: 'POST' }); ElMessage.success('Apple Music 交接已重新提交'); await store.fetchTasks() } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : 'Apple Music 交接重试失败') } }
const cancel = async (id: string) => { try { await request(`/api/tasks/${id}/cancel`, { method: 'POST' }); ElMessage.success('任务已取消'); await store.fetchTasks() } catch (error) { ElMessage.error(error instanceof Error ? error.message : '取消任务失败') } }
const deleteSelected = async () => {
  if (!selectedIds.value.length) return
  try { await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 条任务记录吗？删除后无法恢复。`, '删除任务记录', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }); actionLoading.value = true; await request('/api/tasks/batch-delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_ids: selectedIds.value }) }); selectedIds.value = []; ElMessage.success('已删除选中的任务记录'); await store.fetchTasks() } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error instanceof Error ? error.message : '删除任务记录失败') } finally { actionLoading.value = false }
}
</script>

<template>
  <div class="operation-page product-page">
    <header class="hero"><div><span>操作中心</span><h1>操作记录与运行日志</h1><p>集中查看转换任务与服务运行信息，记录保持精简、清晰且可追溯。</p></div><div class="summary"><i>转换中<b>{{ counts.converting }}</b></i><i>等待<b>{{ counts.waiting }}</b></i><i>失败<b>{{ counts.failed }}</b></i></div></header>
    <section class="shell"><nav class="tabs"><button :class="{ active: view === 'records' }" @click="view = 'records'">操作记录</button><button :class="{ active: view === 'logs' }" @click="view = 'logs'">运行日志</button></nav>
      <main>
        <template v-if="view === 'records'"><header class="heading"><div><h2>全部操作</h2><p>显示转换与 Apple Music 交接状态，不显示文件路径和封面。</p></div><em>{{ filteredTasks.length }} 条记录</em></header>
          <div class="filters"><el-input v-model="keyword" placeholder="搜索文件名或转换方案" clearable /><el-select v-model="status"><el-option label="全部状态" value="all" /><el-option label="等待" value="waiting" /><el-option label="转换中" value="converting" /><el-option label="成功" value="success" /><el-option label="失败" value="failed" /><el-option label="已取消" value="cancelled" /></el-select><el-button v-if="selectedIds.length" type="danger" plain :loading="actionLoading" @click="deleteSelected">删除 {{ selectedIds.length }} 条</el-button></div>
          <div class="list" v-loading="store.loading"><article v-for="task in tasks" :key="task.id" class="row"><el-checkbox :model-value="selectedIds.includes(task.id)" :aria-label="`选择 ${fileName(task.source_file)}`" @change="toggle(task.id)" /><div class="main"><strong>{{ fileName(task.source_file) }}</strong><span>{{ profileName(task.profile_id) }}</span><div v-if="task.apple_music_status" class="handoff"><el-tag size="small" :type="appleMusicType(task.apple_music_status)" effect="light">{{ appleMusicLabel(task.apple_music_status) }}</el-tag><small v-if="task.apple_music_error">{{ task.apple_music_error }}</small></div></div><el-tag :type="taskType(task.status)" effect="light">{{ taskLabel(task.status) }}</el-tag><small v-if="task.status === 'converting'">{{ task.progress || 0 }}%</small><time>{{ dateTime(task.end_time || task.start_time) }}</time><div class="actions"><el-button v-if="task.status === 'failed'" type="warning" link @click="retry(task.id)">重试</el-button><el-button v-if="['failed', 'received'].includes(task.apple_music_status || '')" type="warning" link @click="retryAppleMusic(task.id, task.apple_music_status === 'received')">{{ task.apple_music_status === 'received' ? '再次交接' : '重试交接' }}</el-button><el-button v-if="['waiting', 'converting'].includes(task.status)" type="danger" link @click="cancel(task.id)">取消</el-button></div></article><el-empty v-if="!tasks.length && !store.loading" description="暂无匹配的操作记录" :image-size="76" /></div>
          <TablePagination v-if="filteredTasks.length > taskPageSize" v-model:current-page="page" v-model:page-size="taskPageSize" :total="filteredTasks.length" :page-sizes="[100]" /></template>
        <template v-else><header class="heading"><div><h2>运行日志</h2><p>显示服务运行摘要，不再提供单条日志的检测详情面板。</p></div><em>每 5 秒更新</em></header><div class="filters"><el-input v-model="keyword" placeholder="搜索模块或日志内容" clearable /><el-select v-model="level"><el-option label="全部等级" value="all" /><el-option label="信息" value="INFO" /><el-option label="警告" value="WARNING" /><el-option label="错误" value="ERROR" /><el-option label="调试" value="DEBUG" /></el-select><el-button @click="store.fetchLogs(200)">刷新</el-button></div><div class="list logs" v-loading="store.loading"><article v-for="log in paginatedLogs" :key="`${log.timestamp}-${log.module}-${log.message}`" class="row"><time>{{ dateTime(log.timestamp) }}</time><el-tag :type="logType(log.level)" effect="light">{{ log.level }}</el-tag><span>{{ log.module }}</span><p>{{ log.message }}</p></article><el-empty v-if="!logs.length && !store.loading" description="暂无运行日志" :image-size="76" /></div><TablePagination v-if="logs.length > logPageSize" v-model:current-page="logPage" v-model:page-size="logPageSize" :total="logs.length" :page-sizes="[200]" /></template>
      </main>
    </section>
  </div>
</template>

<style scoped>
.operation-page{padding-bottom:32px}.hero{display:flex;justify-content:space-between;gap:28px;padding:30px 34px;margin-bottom:16px;border:1px solid #ece8fb;border-radius:24px;background:linear-gradient(120deg,#fff 40%,#f7f3ff)}.hero>div>span{display:inline-flex;padding:5px 10px;border-radius:99px;background:#f0e9ff;color:#8e67ea;font-size:12px;font-weight:700}.hero h1{margin:10px 0 8px;color:#202b3e;font-size:30px}.hero p{margin:0;color:#8390a6}.summary{display:grid;grid-template-columns:repeat(3,minmax(84px,1fr));gap:10px;align-self:center}.summary i{display:grid;gap:4px;padding:13px 16px;border:1px solid #eeeaf7;border-radius:16px;background:#fff;color:#8d97a9;font-size:12px;font-style:normal}.summary b{color:#2c3850;font-size:21px}.shell{display:grid;grid-template-columns:220px minmax(0,1fr);overflow:hidden;border:1px solid #ecebf4;border-radius:22px;background:#fff}.tabs{display:flex;flex-direction:column;gap:8px;padding:18px 14px;border-right:1px solid #eeeef5;background:#fcfbff}.tabs button{padding:13px 16px;border:0;border-radius:12px;background:transparent;color:#68758b;text-align:left;font-weight:700;cursor:pointer}.tabs button.active{background:#eee7ff;color:#7a54dc}main{min-width:0;padding:24px}.heading{display:flex;justify-content:space-between;gap:18px;align-items:start;margin-bottom:18px}.heading h2{margin:0 0 6px;color:#253149;font-size:22px}.heading p{margin:0;color:#929caf;font-size:13px}.heading em{padding:7px 10px;border-radius:8px;background:#f3efff;color:#8b65e7;font-size:12px;font-style:normal;white-space:nowrap}.filters{display:flex;gap:10px;align-items:center;margin-bottom:14px}.filters .el-input{max-width:300px}.filters .el-select{width:130px}.list{overflow:hidden;border:1px solid #efedf5;border-radius:16px}.row{display:grid;grid-template-columns:30px minmax(190px,1fr) 88px 52px 170px 56px;gap:12px;align-items:center;min-height:68px;padding:10px 16px;border-bottom:1px solid #f0eef5}.row:last-child{border-bottom:0}.main{display:grid;min-width:0;gap:5px}.main strong,.main span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.main strong{color:#34415a;font-size:14px}.main span{color:#8d98aa;font-size:12px}.row time{color:#7d899e;font-size:12px;white-space:nowrap}.row small{color:#9a72eb;font-size:12px}.actions{text-align:right}.logs .row{grid-template-columns:minmax(142px,170px) 84px minmax(150px,220px) minmax(0,1fr)}.logs p,.logs .row>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.logs p{margin:0;color:#536078;font-size:13px;line-height:1.5}.logs .row>span{color:#7e63bb;font-size:12px}.pager{display:flex;justify-content:flex-end;gap:12px;align-items:center;padding-top:16px;color:#7f8aa0;font-size:13px}@media(max-width:760px){.operation-page{padding-bottom:100px}.hero{display:block;padding:22px 20px;border-radius:18px}.hero h1{font-size:24px}.hero p{font-size:13px;line-height:1.6}.summary{margin-top:18px}.shell{display:block;border-radius:18px}.tabs{flex-direction:row;padding:10px;border-right:0;border-bottom:1px solid #eeeef5}.tabs button{flex:1;padding:10px;text-align:center}main{padding:20px 14px}.heading h2{font-size:19px}.heading p{line-height:1.5}.filters{display:grid;grid-template-columns:minmax(0,1fr) 108px}.filters .el-input{max-width:none}.filters .el-select{width:100%}.filters .el-button{grid-column:1/-1;justify-self:start}.row{grid-template-columns:24px minmax(0,1fr) auto;gap:8px 10px;min-height:0;padding:16px 14px}.main{grid-column:2/-1}.row>.el-tag{grid-column:2;justify-self:start}.row time{grid-column:3;grid-row:3;align-self:end;font-size:11px}.row small{grid-column:2}.actions{grid-column:3;grid-row:2}.logs .row{grid-template-columns:84px minmax(0,1fr);gap:8px 12px}.logs .row time{grid-column:1;grid-row:1;font-size:11px}.logs .row>.el-tag{grid-column:2;justify-self:start}.logs .row>span{grid-column:1;grid-row:2;max-width:84px}.logs p{grid-column:2;grid-row:2;min-width:0;white-space:normal;word-break:break-word}.pager{justify-content:center}}
@media (max-width:760px) { .logs .row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:9px 12px; padding:16px 14px; }.logs .row time { grid-column:1; grid-row:1; }.logs .row > .el-tag { grid-column:2; grid-row:1; justify-self:end; }.logs .row > span { grid-column:1 / -1; grid-row:2; max-width:none; overflow:visible; white-space:normal; }.logs .row p { grid-column:1 / -1; grid-row:3; min-width:0; white-space:normal; word-break:break-word; } }
.handoff{display:flex;align-items:center;gap:6px;min-width:0}.handoff small{overflow:hidden;color:#cf5a5a;text-overflow:ellipsis;white-space:nowrap}.actions{display:grid;justify-items:end}
</style>
