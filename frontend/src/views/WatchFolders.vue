<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { WatchFolder, WatchFolderEvent } from '../types'
import WatchFolderEditorDialog from '../components/WatchFolderEditorDialog.vue'

const store = useAppStore()
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const selectedFolder = ref<WatchFolder | null>(null)
const showEventsDialog = ref(false)
const selectedFolderName = ref('')
const watchEvents = ref<WatchFolderEvent[]>([])
const eventsLoading = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | undefined

const newFolder = ref({
  name: '',
  inputDir: '',
  profileIds: [] as string[],
  autoProcess: true,
  recursiveScan: true,
  scanIntervalMinutes: 5,
  outputDir: '/mnt/d/Music/output',
})

const editFolder = ref({
  name: '',
  inputDir: '',
  profileIds: [] as string[],
  autoProcess: true,
  recursiveScan: true,
  scanIntervalMinutes: 5,
  outputDir: '',
})

onMounted(async () => {
  await Promise.all([store.fetchWatchFolders(), store.fetchProfiles()])
  refreshTimer = setInterval(() => store.fetchWatchFolders(true), 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

const enabledCount = computed(() => store.watchFolders.filter(folder => folder.enabled).length)
const watchingCount = computed(() => store.watchFolders.filter(folder => folder.watching).length)
const errorCount = computed(() => store.watchFolders.filter(folder => folder.lastError).length)
const selectedProfiles = computed(() => store.profiles.filter(profile => selectedFolder.value?.profileIds.includes(profile.id)))

watch(
  () => store.watchFolders,
  folders => {
    if (!folders.length) {
      selectedFolder.value = null
      return
    }
    selectedFolder.value = folders.find(folder => folder.id === selectedFolder.value?.id) || folders[0]
  },
  { immediate: true, deep: true },
)

watch(
  () => selectedFolder.value?.id,
  async id => {
    watchEvents.value = []
    if (!id) return
    try {
      watchEvents.value = await store.fetchWatchFolderEvents(id)
    } catch {
      // 详情区保留为空，不影响目录操作。
    }
  },
)

const formatTime = (value?: string) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

const handleCreate = async () => {
  console.log('>>> handleCreate called! <<<')
  console.log('>>> form data:', JSON.stringify(newFolder.value))
  try {
    await store.createWatchFolder(newFolder.value)
    ElMessage.success('监控目录创建成功')
    showCreateDialog.value = false
    // 重置表单
    newFolder.value = {
      name: '',
      inputDir: '',
      profileIds: [],
      autoProcess: true,
      recursiveScan: true,
      scanIntervalMinutes: 5,
      outputDir: '/mnt/d/Music/output',
    }
  } catch (error) {
    console.error('>>> handleCreate error:', error)
    ElMessage.error('创建失败')
  }
}

const handleEdit = (folder: WatchFolder) => {
  selectedFolder.value = folder
  editFolder.value = {
    name: folder.name,
    inputDir: folder.inputDir,
    profileIds: folder.profileIds || [],
    autoProcess: folder.autoProcess,
    recursiveScan: folder.recursiveScan,
    scanIntervalMinutes: folder.scanIntervalMinutes,
    outputDir: folder.outputDir || '',
  }
  showEditDialog.value = true
}

const handleUpdate = async () => {
  console.log('>>> handleUpdate called! <<<')
  console.log('>>> form data:', JSON.stringify(editFolder.value))
  if (!selectedFolder.value) return
  try {
    await store.updateWatchFolder(selectedFolder.value.id, editFolder.value)
    ElMessage.success('监控目录更新成功')
    showEditDialog.value = false
  } catch (error) {
    console.error('>>> handleUpdate error:', error)
    ElMessage.error('更新失败')
  }
}

const handleScan = async (folderId: string) => {
  try {
    const result = await store.scanWatchFolder(folderId)
    ElMessage.success(`扫描完成，发现 ${result.files?.length || 0} 个文件`)
  } catch (error) {
    ElMessage.error('扫描失败')
  }
}

const handleDelete = async (id: string) => {
  try {
    await ElMessageBox.confirm('确定要删除这个监控目录吗？', '确认', {
      type: 'warning',
    })
    await store.deleteWatchFolder(id)
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleTriggerConvert = async (folderId: string) => {
  try {
    const result = await store.processWatchFolder(folderId)
    if (!result.files?.length) {
      ElMessage.warning('目录中没有找到音频文件')
      return
    }
    ElMessage.success(`扫描完成，已创建 ${result.created_tasks} 个转换任务`)
  } catch (error) {
    ElMessage.error('触发转换失败')
  }
}

const handleToggle = async (folder: WatchFolder) => {
  try {
    const updated = await store.toggleWatchFolder(folder.id)
    ElMessage.success(updated.enabled ? '实时监控已启用' : '实时监控已停用')
  } catch (error) {
    ElMessage.error('切换监控状态失败')
  }
}

const handleEvents = async (folder: WatchFolder) => {
  selectedFolderName.value = folder.name
  showEventsDialog.value = true
  eventsLoading.value = true
  try {
    watchEvents.value = await store.fetchWatchFolderEvents(folder.id)
  } catch (error) {
    ElMessage.error('获取监控事件失败')
  } finally {
    eventsLoading.value = false
  }
}
</script>

<template>
  <div class="watch-folders-page product-page">
    <div class="page-header">
      <div class="page-title-block">
        <h1>监控目录</h1>
        <p>持续监听 NAS 文件夹，自动发现并按指定方案转换新音乐。</p>
      </div>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        添加监控目录
      </el-button>
    </div>

    <div class="watch-summary">
      <div><span>监控目录</span><strong>{{ store.watchFolders.length }}</strong></div>
      <div><span>已启用</span><strong>{{ enabledCount }}</strong></div>
      <div><span>正在监听</span><strong class="success-value">{{ watchingCount }}</strong></div>
      <div><span>异常目录</span><strong :class="{ 'danger-value': errorCount }">{{ errorCount }}</strong></div>
    </div>

    <div class="watch-workspace" v-loading="store.loading">
      <section class="watch-table-panel">
        <div class="table-toolbar"><div><strong>目录列表</strong><span>状态每 5 秒自动更新</span></div><el-button @click="store.fetchWatchFolders()"><el-icon><Refresh /></el-icon>刷新</el-button></div>
        <el-table :data="store.watchFolders" highlight-current-row height="540" @current-change="(row: WatchFolder) => selectedFolder = row">
          <el-table-column label="状态" width="86"><template #default="{ row }"><span class="state-pill" :class="{ active: row.watching, disabled: !row.enabled, error: row.enabled && !row.watching }"><i></i>{{ !row.enabled ? '停用' : row.watching ? '监听中' : '异常' }}</span></template></el-table-column>
          <el-table-column label="目录" min-width="230"><template #default="{ row }"><div class="folder-cell"><strong>{{ row.name }}</strong><code>{{ row.inputDir }}</code></div></template></el-table-column>
          <el-table-column label="方案" width="118"><template #default="{ row }">{{ row.profileIds.length }} 个方案</template></el-table-column>
          <el-table-column label="最近扫描" width="150"><template #default="{ row }"><div class="scan-cell"><span>{{ formatTime(row.lastScan) }}</span><small>{{ row.lastScanCount }} 个文件</small></div></template></el-table-column>
          <el-table-column label="任务" width="76" align="right"><template #default="{ row }"><strong>{{ row.createdTasks }}</strong></template></el-table-column>
        </el-table>
      </section>

      <aside v-if="selectedFolder" class="watch-inspector">
        <div class="folder-heading"><div class="folder-mark"><el-icon><FolderOpened /></el-icon></div><div><span class="eyebrow">监控详情</span><h2>{{ selectedFolder.name }}</h2></div></div>
        <div class="health-banner" :class="{ error: selectedFolder.lastError, idle: !selectedFolder.watching }"><span class="health-icon"><el-icon><CircleCheck v-if="selectedFolder.watching && !selectedFolder.lastError" /><Warning v-else /></el-icon></span><div><strong>{{ selectedFolder.lastError ? '监控发生异常' : selectedFolder.watching ? '目录运行正常' : '目录当前未监听' }}</strong><small>{{ selectedFolder.lastError || selectedFolder.lastEvent || '等待新的文件事件' }}</small></div></div>
        <section class="inspector-section"><h3>运行信息</h3><dl><div><dt>输入目录</dt><dd><code>{{ selectedFolder.inputDir }}</code></dd></div><div><dt>输出目录</dt><dd><code>{{ selectedFolder.outputDir || '使用默认目录' }}</code></dd></div><div><dt>下次扫描</dt><dd>{{ formatTime(selectedFolder.nextScanAt) }}</dd></div><div><dt>扫描方式</dt><dd>{{ selectedFolder.recursiveScan ? '递归扫描' : '仅当前目录' }} · {{ selectedFolder.autoProcess ? '自动处理' : '手动处理' }}</dd></div></dl></section>
        <section class="inspector-section"><h3>转换方案</h3><div class="profile-chips"><el-tag v-for="profile in selectedProfiles" :key="profile.id" effect="plain">{{ profile.name }}</el-tag><span v-if="!selectedProfiles.length" class="empty-copy">尚未关联方案</span></div></section>
        <section class="inspector-section events-section"><div class="section-heading"><h3>最近事件</h3><el-button link type="primary" @click="handleEvents(selectedFolder)">查看全部</el-button></div><div v-if="watchEvents.length" class="event-list"><div v-for="event in watchEvents.slice(0, 3)" :key="`${event.timestamp}-${event.message}`"><i></i><p><strong>{{ event.type }}</strong><span>{{ event.message }}</span><small>{{ formatTime(event.timestamp) }}</small></p></div></div><span v-else class="empty-copy">暂无监控事件</span></section>
        <div class="inspector-buttons"><el-button type="primary" @click="handleTriggerConvert(selectedFolder.id)"><el-icon><VideoPlay /></el-icon>立即转换</el-button><el-button @click="handleScan(selectedFolder.id)"><el-icon><Search /></el-icon>扫描</el-button><el-button @click="handleEdit(selectedFolder)"><el-icon><Edit /></el-icon>编辑</el-button><el-button :type="selectedFolder.enabled ? 'warning' : 'success'" plain @click="handleToggle(selectedFolder)">{{ selectedFolder.enabled ? '停用' : '启用' }}</el-button></div>
        <el-button class="delete-folder" type="danger" link @click="handleDelete(selectedFolder.id)"><el-icon><Delete /></el-icon>删除监控目录</el-button>
      </aside>
    </div>

    <!-- 创建对话框 -->
    <el-dialog
      v-if="false"
      v-model="showCreateDialog"
      title="添加监控目录"
      width="760px"
    >
      <el-form :model="newFolder" label-position="top" class="watch-folder-form">
        <div class="form-section-title">目录设置</div>
        <el-form-item class="form-item-full">
          <template #label>名称<el-tooltip content="用于识别这条监控规则。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="newFolder.name" placeholder="例如：下载音乐" />
        </el-form-item>

        <el-form-item class="form-item-full">
          <template #label>输入目录<el-tooltip content="需要持续扫描和监听的音乐源目录，必须填写 WSL 绝对路径。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="newFolder.inputDir" placeholder="/music/source" />
        </el-form-item>

        <el-form-item class="form-item-full">
          <template #label>输出目录<el-tooltip content="转换成品保存的位置；建议与 Apple Music 自动导入目录分开。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="newFolder.outputDir" placeholder="/music/output" />
        </el-form-item>

        <div class="form-section-title form-item-full">转换设置</div>
        <el-form-item class="form-item-full">
          <template #label>转换配置<el-tooltip content="选择此目录中的音乐需要使用的一个或多个转换配置。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="newFolder.profileIds" multiple placeholder="选择转换配置">
            <el-option
              v-for="profile in store.profiles"
              :key="profile.id"
              :label="profile.name"
              :value="profile.id"
            />
          </el-select>
        </el-form-item>

        <div class="form-section-title form-item-full">处理方式</div>
        <el-form-item>
          <template #label>自动处理<el-tooltip content="开启后，发现稳定的音频文件会自动创建转换任务。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-switch v-model="newFolder.autoProcess" />
        </el-form-item>

        <el-form-item>
          <template #label>递归扫描<el-tooltip content="开启后，会同时扫描输入目录下的所有子目录。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-switch v-model="newFolder.recursiveScan" />
        </el-form-item>

      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog
      v-if="false"
      v-model="showEditDialog"
      title="编辑监控目录"
      width="760px"
    >
      <el-form :model="editFolder" label-position="top" class="watch-folder-form">
        <div class="form-section-title">目录设置</div>
        <el-form-item class="form-item-full">
          <template #label>名称<el-tooltip content="用于识别这条监控规则。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="editFolder.name" placeholder="例如：下载音乐" />
        </el-form-item>

        <el-form-item class="form-item-full">
          <template #label>输入目录<el-tooltip content="需要持续扫描和监听的音乐源目录，必须填写 WSL 绝对路径。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="editFolder.inputDir" placeholder="/music/source" />
        </el-form-item>

        <el-form-item class="form-item-full">
          <template #label>输出目录<el-tooltip content="转换成品保存的位置；建议与 Apple Music 自动导入目录分开。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="editFolder.outputDir" placeholder="留空则使用配置或全局默认目录" />
        </el-form-item>

        <div class="form-section-title form-item-full">转换设置</div>
        <el-form-item class="form-item-full">
          <template #label>转换配置<el-tooltip content="选择此目录中的音乐需要使用的一个或多个转换配置。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="editFolder.profileIds" multiple placeholder="选择转换配置">
            <el-option
              v-for="profile in store.profiles"
              :key="profile.id"
              :label="profile.name"
              :value="profile.id"
            />
          </el-select>
        </el-form-item>

        <div class="form-section-title form-item-full">处理方式</div>
        <el-form-item>
          <template #label>自动处理<el-tooltip content="开启后，发现稳定的音频文件会自动创建转换任务。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-switch v-model="editFolder.autoProcess" />
        </el-form-item>

        <el-form-item>
          <template #label>递归扫描<el-tooltip content="开启后，会同时扫描输入目录下的所有子目录。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-switch v-model="editFolder.recursiveScan" />
        </el-form-item>

      </el-form>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUpdate">更新</el-button>
      </template>
    </el-dialog>

    <WatchFolderEditorDialog v-model="showCreateDialog" mode="create" :form="newFolder" :profiles="store.profiles" :file-stable-seconds="store.settings.fileStableSeconds" @submit="handleCreate" />
    <WatchFolderEditorDialog v-model="showEditDialog" mode="edit" :form="editFolder" :profiles="store.profiles" :folder="selectedFolder" :file-stable-seconds="store.settings.fileStableSeconds" @submit="handleUpdate" />

    <el-dialog
      v-model="showEventsDialog"
      :title="`${selectedFolderName} - 监控事件`"
      width="760px"
    >
      <el-table v-loading="eventsLoading" :data="watchEvents" max-height="440">
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.timestamp) }}</template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="110" />
        <el-table-column prop="message" label="详情" min-width="380" />
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
.watch-folders-page {
  padding-bottom: 32px;
}

.watch-summary { display: grid; grid-template-columns: repeat(4, 1fr); margin-bottom: 16px; overflow: hidden; background: #fff; border: 1px solid #e7ece9; border-radius: 14px; }
.watch-summary > div { display: flex; align-items: center; justify-content: space-between; padding: 17px 22px; border-right: 1px solid #edf0ef; }
.watch-summary > div:last-child { border-right: 0; }
.watch-summary span { color: #7f8a86; font-size: 12px; }
.watch-summary strong { color: #26332e; font-size: 23px; }
.watch-summary .success-value { color: #0c9c68; }
.watch-summary .danger-value { color: #e45656; }
.watch-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 360px; min-height: 620px; overflow: hidden; background: #fff; border: 1px solid #e7ece9; border-radius: 16px; box-shadow: 0 12px 36px rgba(18, 58, 45, .05); }
.watch-table-panel { min-width: 0; border-right: 1px solid #e7ece9; }
.table-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 18px 20px; border-bottom: 1px solid #edf0ef; }
.table-toolbar > div { display: flex; flex-direction: column; gap: 4px; }
.table-toolbar strong { color: #26322e; font-size: 15px; }
.table-toolbar span { color: #98a19e; font-size: 11px; }
.state-pill { display: inline-flex; align-items: center; gap: 6px; color: #cf5b4f; font-size: 11px; font-weight: 700; }
.state-pill i { width: 7px; height: 7px; background: #e06458; border-radius: 50%; }
.state-pill.active { color: #087955; }
.state-pill.active i { background: #0c9c68; box-shadow: 0 0 0 3px #e1f4ed; }
.state-pill.disabled { color: #919b97; }
.state-pill.disabled i { background: #aab2af; }
.folder-cell, .scan-cell { display: flex; min-width: 0; flex-direction: column; gap: 5px; }
.folder-cell strong { color: #2b3833; font-size: 13px; }
.folder-cell code { overflow: hidden; color: #7e8a85; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.scan-cell span { color: #3e4a46; font-size: 11px; }
.scan-cell small { color: #9aa39f; font-size: 10px; }
.watch-inspector { min-width: 0; padding: 23px; background: #fbfcfc; }
.folder-heading { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
.folder-mark { display: grid; width: 44px; height: 44px; place-items: center; background: #e3f3ed; color: #0b8c62; border-radius: 11px; font-size: 21px; }
.eyebrow { display: block; margin-bottom: 3px; color: #0c9c68; font-size: 10px; font-weight: 800; letter-spacing: .1em; }
.folder-heading h2 { margin: 0; color: #23302b; font-size: 19px; }
.health-banner { display: flex; align-items: flex-start; gap: 11px; padding: 14px; margin-bottom: 19px; background: #eaf7f2; border: 1px solid #cdebe0; border-radius: 11px; }
.health-banner.error { background: #fff0ef; border-color: #f4d2cf; }
.health-banner.idle { background: #f3f5f4; border-color: #e4e8e6; }
.health-icon { display: grid; width: 28px; height: 28px; flex: 0 0 28px; place-items: center; color: #0c9c68; background: #fff; border-radius: 50%; }
.health-banner.error .health-icon { color: #df584e; }
.health-banner > div { display: flex; min-width: 0; flex-direction: column; gap: 4px; }
.health-banner strong { color: #2c3934; font-size: 12px; }
.health-banner small { overflow: hidden; color: #77847f; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.inspector-section { padding: 15px 0; border-top: 1px solid #e7ebe9; }
.inspector-section h3 { margin: 0 0 12px; color: #53605b; font-size: 11px; font-weight: 800; letter-spacing: .04em; }
.inspector-section dl { margin: 0; }
.inspector-section dl > div { display: flex; justify-content: space-between; gap: 14px; min-height: 29px; }
.inspector-section dt { flex: 0 0 auto; color: #969f9b; font-size: 10px; }
.inspector-section dd { min-width: 0; margin: 0; overflow: hidden; color: #3c4944; font-size: 11px; font-weight: 600; text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.inspector-section code { font-size: 9px; }
.profile-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.empty-copy { color: #9ba4a0; font-size: 11px; }
.section-heading { display: flex; align-items: center; justify-content: space-between; }
.section-heading h3 { margin-bottom: 0; }
.event-list { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
.event-list > div { display: flex; gap: 9px; }
.event-list i { width: 6px; height: 6px; margin-top: 5px; background: #0c9c68; border-radius: 50%; }
.event-list p { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 2px; margin: 0; }
.event-list strong, .event-list span, .event-list small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.event-list strong { color: #53605b; font-size: 10px; text-transform: uppercase; }
.event-list span { color: #35423d; font-size: 11px; }
.event-list small { color: #9ba49f; font-size: 9px; }
.inspector-buttons { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; padding-top: 16px; border-top: 1px solid #e7ebe9; }
.delete-folder { width: 100%; margin-top: 10px; }

.watch-status {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  font-size: 12px;
  color: #606266;
}

.watch-status :deep(.el-tag) {
  font-weight: 600;
}

.status-error {
  color: #f56c6c;
}

.operation-buttons {
  display: grid;
  grid-template-columns: repeat(3, max-content);
  gap: 4px 12px;
  align-items: center;
}

.operation-buttons :deep(.el-button + .el-button) {
  margin-left: 0;
}

.watch-folder-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 20px;
}

.watch-folder-form :deep(.el-form-item) {
  min-width: 0;
  margin-bottom: 18px;
}

.watch-folder-form :deep(.el-form-item__label) {
  width: auto !important;
  height: auto;
  padding: 0 0 8px;
  color: #303133;
  font-weight: 500;
  line-height: 20px;
}

.watch-folder-form :deep(.el-form-item__content) {
  min-width: 0;
}

.form-item-full {
  grid-column: 1 / -1;
}

.form-section-title {
  grid-column: 1 / -1;
  margin: 4px 0 14px;
  padding-left: 10px;
  color: #0c9c68;
  border-left: 3px solid #0c9c68;
  font-size: 15px;
  font-weight: 600;
  line-height: 20px;
}

.field-help {
  margin-left: 4px;
  color: #909399;
  cursor: help;
  vertical-align: -2px;
}

:deep(.el-card__body) {
  overflow: hidden;
  border-radius: 12px;
}

:deep(.el-dialog) {
  border-radius: 14px;
}

@media (max-width: 700px) {
  .watch-summary { grid-template-columns: repeat(2, 1fr); }
  .watch-workspace { grid-template-columns: 1fr; }
  .watch-table-panel { border-right: 0; border-bottom: 1px solid #e7ece9; }
  .watch-folder-form {
    grid-template-columns: 1fr;
  }
}
</style>
