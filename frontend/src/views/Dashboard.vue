<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import type { Task } from '../types'

const store = useAppStore()
const router = useRouter()
const coverErrors = ref(new Set<string>())
const currentTask = computed(() => store.tasks.find(task => task.status === 'converting') || null)
const recentTasks = computed(() => store.tasks.filter(task => task.status === 'success').slice(0, 5))
const exceptions = computed(() => store.tasks.filter(task => task.status === 'failed').slice(0, 4))
const activeWatchFolders = computed(() => store.watchFolders.filter(folder => folder.enabled && folder.watching).length)
const fileName = (path?: string) => path?.split('/').pop() || '--'
const getFileForTask = (task?: Task | null) => task ? store.files.find(file => file.path.replace(/\\/g, '/') === task.source_file?.replace(/\\/g, '/')) : undefined
const coverUrl = (task?: Task | null) => { const file = getFileForTask(task); return file ? `/api/files/${file.id}/cover` : '' }
const markCoverError = (id: string) => { coverErrors.value.add(id); coverErrors.value = new Set(coverErrors.value) }
const artist = (task?: Task | null) => getFileForTask(task)?.artist || '未知艺术家'
const album = (task?: Task | null) => getFileForTask(task)?.album || '未知专辑'
const profileName = (id?: string) => store.profiles.find(profile => profile.id === id)?.name || id || '--'
const formatTime = (time?: string) => time ? new Date(time).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '--'
const handoffLabel = (task: Task) => task.apple_music_status
  ? ({ received: '已接收', waiting: '等待接收', failed: '交接失败' }[task.apple_music_status] || '未交接')
  : '未交接'
onMounted(() => Promise.all([store.fetchFiles(), store.fetchTasks(), store.fetchProfiles(), store.fetchWatchFolders()]))
</script>

<template>
  <div class="health-dashboard">
    <section class="health-strip">
      <span><el-icon><CircleCheck /></el-icon>系统运行正常</span><span>监控目录 <strong>{{ activeWatchFolders }} / {{ store.watchFolders.length }}</strong> 正常</span><span>转换任务 <strong>{{ currentTask ? 1 : 0 }}</strong> 个进行中</span><span>异常 <strong>{{ exceptions.length }}</strong> 个待处理</span>
      <el-button type="primary" @click="router.push('/files')"><el-icon><VideoPlay /></el-icon>开始转换</el-button>
    </section>
    <div class="dashboard-grid top-grid">
      <section class="dashboard-panel active-conversion">
        <div class="panel-title"><h2>正在进行的转换</h2><el-button link type="primary" @click="router.push('/tasks')">查看全部任务</el-button></div>
        <template v-if="currentTask">
          <div class="hero-track"><div class="hero-cover"><img v-if="coverUrl(currentTask) && !coverErrors.has(currentTask.id)" :src="coverUrl(currentTask)" :alt="`${fileName(currentTask.source_file)} 封面`" @error="markCoverError(currentTask.id)" /><el-icon v-else><Headset /></el-icon></div><div><h3>{{ fileName(currentTask.source_file) }}</h3><p>{{ artist(currentTask) }} · {{ album(currentTask) }}</p><small>{{ currentTask.source_file }}</small><span>{{ profileName(currentTask.profile_id) }}</span></div></div>
          <div class="hero-progress"><el-progress :percentage="currentTask.progress || 0" :show-text="false" :stroke-width="8" /><strong>{{ currentTask.progress || 0 }}%</strong></div><div class="progress-meta"><span>当前任务正在处理</span><span>输出至 {{ currentTask.output_file || '默认目录' }}</span></div>
        </template>
        <div v-else class="dashboard-empty"><el-icon><CircleCheck /></el-icon><strong>转换队列空闲</strong><span>从音乐库选择文件即可创建任务。</span><el-button plain @click="router.push('/files')">浏览音乐库</el-button></div>
      </section>
      <section class="dashboard-panel watch-health">
        <div class="panel-title"><h2>监控目录健康状态</h2><el-button link type="primary" @click="router.push('/watch-folders')">管理监控目录</el-button></div>
        <div class="watch-head"><span>目录</span><span>状态</span><span>最后扫描</span><span>方案</span></div>
        <div v-for="folder in store.watchFolders.slice(0, 3)" :key="folder.id" class="watch-row"><strong>{{ folder.inputDir }}</strong><span :class="folder.watching ? 'healthy' : 'paused'">{{ folder.watching ? '正常' : '已暂停' }}</span><span>{{ formatTime(folder.lastScan) }}</span><span>{{ folder.profileIds.map(profileName).join('、') || '--' }}</span></div>
        <div v-if="!store.watchFolders.length" class="inline-empty">暂无监控目录</div><footer><span><el-icon><CircleCheck /></el-icon>{{ activeWatchFolders }} 个目录正在监听</span><span>每 5 秒自动刷新</span></footer>
      </section>
    </div>
    <div class="dashboard-grid bottom-grid">
      <section class="dashboard-panel recent-music">
        <div class="panel-title"><h2>最近处理的音乐</h2><el-button link type="primary" @click="router.push('/tasks')">查看全部</el-button></div><div class="recent-head"><span>音乐</span><span>输出方案</span><span>完成时间</span><span>交接状态</span></div>
        <div v-for="task in recentTasks" :key="task.id" class="recent-item"><div class="mini-cover"><img v-if="coverUrl(task) && !coverErrors.has(task.id)" :src="coverUrl(task)" :alt="`${fileName(task.source_file)} 封面`" loading="lazy" @error="markCoverError(task.id)" /><el-icon v-else><Headset /></el-icon></div><div><strong>{{ fileName(task.source_file) }}</strong><small>{{ artist(task) }}</small></div><span>{{ profileName(task.profile_id) }}</span><span>{{ formatTime(task.end_time) }}</span><el-tag :type="task.apple_music_status === 'received' ? 'success' : task.apple_music_status === 'failed' ? 'danger' : 'warning'" size="small">{{ handoffLabel(task) }}</el-tag></div>
        <div v-if="!recentTasks.length" class="inline-empty">暂无已完成任务</div>
      </section>
      <section class="dashboard-panel exception-panel">
        <div class="panel-title"><h2>异常与需要处理</h2><el-button link type="primary" @click="router.push('/logs')">查看日志</el-button></div>
        <div v-for="task in exceptions" :key="task.id" class="exception-row"><el-icon><WarningFilled /></el-icon><div><strong>{{ fileName(task.source_file) }}</strong><span>{{ task.error || '转换失败，请查看日志了解详情。' }}</span></div><el-button link type="primary" @click="router.push('/tasks')">处理</el-button></div>
        <div v-if="!exceptions.length" class="dashboard-empty compact"><el-icon><CircleCheck /></el-icon><strong>没有待处理异常</strong><span>所有转换与交接流程运行正常。</span></div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.health-dashboard { max-width: 1320px; margin: 0 auto; padding: 16px 0 32px; }.health-dashboard :deep(.el-button--primary) { border-color: #0c9c68; background: #0c9c68; }.health-dashboard :deep(.el-button--primary.is-link) { border-color: transparent; background: transparent; color: #0c9c68; }.health-strip { display: flex; gap: 22px; align-items: center; min-height: 62px; border-bottom: 1px solid #dfe4df; color: #4d5c54; font-size: 13px; }.health-strip > span { display: flex; gap: 7px; align-items: center; white-space: nowrap; }.health-strip > span + span { padding-left: 22px; border-left: 1px solid #dfe4df; }.health-strip .el-icon, .health-strip strong { color: #0c9c68; }.health-strip .el-button { margin-left: auto; }.dashboard-grid { display: grid; gap: 20px; margin-top: 20px; }.top-grid { grid-template-columns: 1fr 1.08fr; }.bottom-grid { grid-template-columns: 1.16fr .84fr; }.dashboard-panel { border: 1px solid #dfe4df; border-radius: 10px; background: #fffefa; overflow: hidden; }.panel-title { display: flex; justify-content: space-between; align-items: center; min-height: 58px; padding: 0 18px; border-bottom: 1px solid #e2e7e3; }.panel-title h2 { margin: 0; color: #25342c; font-size: 16px; }
.hero-track { display: grid; grid-template-columns: 138px 1fr; gap: 20px; padding: 24px 20px 18px; }.hero-cover { display: grid; width: 138px; height: 138px; place-items: center; overflow: hidden; border-radius: 8px; background: #e3f0e9; color: #12895f; font-size: 44px; }.hero-cover img, .mini-cover img { width: 100%; height: 100%; object-fit: cover; }.hero-track h3 { margin: 8px 0 6px; overflow: hidden; color: #1f2d26; font-size: 19px; text-overflow: ellipsis; white-space: nowrap; }.hero-track p, .hero-track small { display: block; overflow: hidden; color: #78857d; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.hero-track small { margin: 14px 0; }.hero-track span { color: #56655d; font-size: 12px; }.hero-progress { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: center; padding: 0 20px; }.hero-progress strong { color: #0c9c68; font-size: 23px; }.progress-meta { display: flex; justify-content: space-between; padding: 12px 20px 20px; color: #829087; font-size: 11px; }
.watch-head, .watch-row { display: grid; grid-template-columns: 1.55fr .55fr .7fr 1fr; gap: 12px; align-items: center; padding: 0 18px; }.watch-head { min-height: 40px; background: #f5f7f4; color: #7e8b83; font-size: 11px; }.watch-row { min-height: 72px; border-top: 1px solid #e7ebe7; color: #65736b; font-size: 11px; }.watch-row strong { overflow: hidden; color: #34423a; font-weight: 500; text-overflow: ellipsis; }.healthy { color: #0c9c68; }.healthy::before, .paused::before { display: inline-block; width: 6px; height: 6px; margin-right: 5px; border-radius: 50%; background: currentColor; content: ''; }.paused { color: #b28b39; }.watch-health footer { display: flex; justify-content: space-between; padding: 12px 18px; border-top: 1px solid #e2e7e3; color: #7e8a83; font-size: 11px; }.watch-health footer span { display: flex; gap: 6px; align-items: center; }.watch-health footer .el-icon { color: #0c9c68; }
.recent-head { display: grid; grid-template-columns: 1.4fr .75fr .65fr .65fr; gap: 12px; align-items: center; min-height: 40px; padding: 0 18px 0 70px; background: #f5f7f4; color: #7f8b84; font-size: 11px; }.recent-item { display: grid; grid-template-columns: 42px minmax(150px, 1.1fr) .75fr .65fr .65fr; gap: 12px; align-items: center; min-height: 64px; padding: 0 18px; border-top: 1px solid #e7ebe7; color: #5e6c64; font-size: 11px; }.mini-cover { display: grid; width: 40px; height: 40px; place-items: center; overflow: hidden; border-radius: 5px; background: #e6f1eb; color: #168d63; }.recent-item > div:nth-child(2) { display: flex; min-width: 0; flex-direction: column; gap: 3px; }.recent-item strong, .recent-item small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.recent-item strong { color: #2c3a32; font-size: 12px; }.recent-item small { color: #87938c; }
.exception-row { display: grid; grid-template-columns: 26px 1fr auto; gap: 10px; align-items: center; min-height: 76px; padding: 10px 18px; border-bottom: 1px solid #e7ebe7; }.exception-row > .el-icon { color: #d49a28; font-size: 20px; }.exception-row > div { display: flex; min-width: 0; flex-direction: column; gap: 4px; }.exception-row strong, .exception-row span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.exception-row strong { color: #34423a; font-size: 12px; }.exception-row span { color: #87938c; font-size: 11px; }.dashboard-empty { display: flex; min-height: 230px; flex-direction: column; gap: 8px; align-items: center; justify-content: center; color: #819087; font-size: 12px; }.dashboard-empty > .el-icon { color: #35aa7c; font-size: 32px; }.dashboard-empty strong { color: #405047; font-size: 14px; }.dashboard-empty.compact { min-height: 245px; }.inline-empty { display: grid; min-height: 160px; place-items: center; color: #8a968f; font-size: 12px; }
@media (max-width: 1100px) { .health-strip > span:nth-of-type(3), .health-strip > span:nth-of-type(4) { display: none; }.top-grid, .bottom-grid { grid-template-columns: 1fr; } } @media (max-width: 700px) { .health-strip > span:nth-of-type(2) { display: none; }.hero-track { grid-template-columns: 88px 1fr; }.hero-cover { width: 88px; height: 88px; }.watch-head, .watch-row { grid-template-columns: 1.4fr .6fr 1fr; }.watch-head > :last-child, .watch-row > :last-child { display: none; } }
</style>
