<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { DeliveryTarget, WatchFolder, WatchFolderEvent } from '../types'
import WatchFolderEditorDialog from '../components/WatchFolderEditorDialog.vue'

const store = useAppStore()
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const selectedFolder = ref<WatchFolder | null>(null)
const showEventsDialog = ref(false)
const showDetailsDialog = ref(false)
const selectedFolderName = ref('')
const watchEvents = ref<WatchFolderEvent[]>([])
const eventsLoading = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | undefined

const newFolder = ref({
  name: '',
  inputDir: '',
  targets: [] as DeliveryTarget[],
  profileIds: [] as string[],
  outputDir: '',
  autoProcess: true,
  recursiveScan: true,
  scanIntervalMinutes: 5,
})

const editFolder = ref({
  name: '',
  inputDir: '',
  targets: [] as DeliveryTarget[],
  profileIds: [] as string[],
  outputDir: '',
  autoProcess: true,
  recursiveScan: true,
  scanIntervalMinutes: 5,
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
const selectedProfiles = computed(() => store.profiles.filter(profile => selectedFolder.value?.targets.some(target => target.type === 'convert' && target.profileId === profile.id)))

const folderTargets = (folder: WatchFolder) => folder.targets.map(target => target.type === 'convert' ? '转换输出' : '原样复制').join('、') || '未配置'

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
      targets: [],
      profileIds: [],
      outputDir: '',
      autoProcess: true,
      recursiveScan: true,
      scanIntervalMinutes: 5,
    }
  } catch (error) {
    console.error('>>> handleCreate error:', error)
    ElMessage.error('创建失败')
  }
}

const handleEdit = (folder: WatchFolder) => {
  showDetailsDialog.value = false
  selectedFolder.value = folder
  editFolder.value = {
    name: folder.name,
    inputDir: folder.inputDir,
    targets: folder.targets.map(target => ({ ...target })),
    profileIds: [],
    outputDir: '',
    autoProcess: folder.autoProcess,
    recursiveScan: folder.recursiveScan,
    scanIntervalMinutes: folder.scanIntervalMinutes,
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
    ElMessage.success(`扫描完成，已创建 ${result.created_tasks} 个转换任务，原样复制 ${result.copied_files || 0} 个文件`)
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
        <p>持续监听下载入口，按一条或多条输出规则处理新音乐。</p>
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
        <div class="watch-list-head"><span>目录</span><span>状态 / 输出规则</span><span>最近扫描</span><span>操作</span></div>
        <article v-for="folder in store.watchFolders" :key="folder.id" class="watch-list-item">
          <div class="folder-cell"><strong>{{ folder.name }}</strong><code>{{ folder.inputDir }}</code></div>
          <div><span class="state-pill" :class="{ active: folder.watching, disabled: !folder.enabled, error: folder.enabled && !folder.watching }"><i></i>{{ !folder.enabled ? '停用' : folder.watching ? '监听中' : '异常' }}</span><small class="target-copy">{{ folderTargets(folder) }}</small></div>
          <div class="scan-cell"><span>{{ formatTime(folder.lastScan) }}</span><small>{{ folder.lastScanCount }} 个文件 · {{ folder.createdTasks }} 任务</small></div>
          <div class="watch-row-actions"><el-button link type="primary" @click="selectedFolder = folder; showDetailsDialog = true">详情</el-button><el-button link @click="handleEdit(folder)">编辑</el-button><el-button link type="danger" @click="handleDelete(folder.id)">删除</el-button><el-button link @click="handleScan(folder.id)">扫描</el-button><el-button link :type="folder.enabled ? 'warning' : 'success'" @click="handleToggle(folder)">{{ folder.enabled ? '停用' : '启用' }}</el-button></div>
        </article>
      </section>

      <el-dialog v-if="selectedFolder" v-model="showDetailsDialog" class="watch-details-dialog" :title="`${selectedFolder.name} - 监控详情`" width="1180px" destroy-on-close>
        <div class="inspector-header">
          <div><div class="eyebrow">监控详情</div><h2>{{ selectedFolder.name }}</h2><p>{{ !selectedFolder.enabled ? '已停用' : selectedFolder.watching ? '正在监听' : '等待监听' }} · {{ selectedFolder.autoProcess ? '自动处理' : '手动处理' }}</p></div>
          <div class="inspector-actions"><el-button type="primary" @click="handleTriggerConvert(selectedFolder.id)">立即处理</el-button><el-button @click="handleScan(selectedFolder.id)">扫描</el-button><el-button @click="handleEdit(selectedFolder)">编辑目录</el-button><el-button :type="selectedFolder.enabled ? 'warning' : 'success'" plain @click="handleToggle(selectedFolder)">{{ selectedFolder.enabled ? '停用' : '启用' }}</el-button></div>
        </div>
        <div class="detail-grid">
          <article class="detail-card">
            <div class="detail-title"><el-icon><FolderOpened /></el-icon><span>运行状态</span></div>
            <dl><div><dt>当前状态</dt><dd><el-tag :type="!selectedFolder.enabled ? 'info' : selectedFolder.watching ? 'success' : 'warning'">{{ !selectedFolder.enabled ? '停用' : selectedFolder.watching ? '监听中' : '未监听' }}</el-tag></dd></div><div><dt>最新消息</dt><dd>{{ selectedFolder.lastError || selectedFolder.lastEvent || '等待新的文件事件' }}</dd></div><div><dt>创建任务</dt><dd>{{ selectedFolder.createdTasks }} 个</dd></div></dl>
          </article>
          <article class="detail-card">
            <div class="detail-title"><el-icon><Folder /></el-icon><span>运行信息</span></div>
            <dl><div><dt>下载目录</dt><dd><code>{{ selectedFolder.inputDir }}</code></dd></div><div><dt>下次扫描</dt><dd>{{ formatTime(selectedFolder.nextScanAt) }}</dd></div><div><dt>扫描方式</dt><dd>{{ selectedFolder.recursiveScan ? '递归扫描' : '仅当前目录' }} · {{ selectedFolder.autoProcess ? '自动处理' : '手动处理' }}</dd></div></dl>
          </article>
          <article class="detail-card wide-card">
            <div class="detail-title"><el-icon><Connection /></el-icon><span>输出规则</span></div>
            <div class="profile-chips"><el-tag v-for="profile in selectedProfiles" :key="profile.id" effect="plain">转换输出：{{ profile.name }}</el-tag><el-tag v-for="(target, index) in selectedFolder.targets.filter(target => target.type === 'copy')" :key="`copy-${target.outputDir}-${index}`" effect="plain">原样复制</el-tag><span v-if="!selectedFolder.targets.length" class="empty-copy">尚未配置输出规则</span></div>
          </article>
          <article class="detail-card">
            <div class="detail-title"><el-icon><Clock /></el-icon><span>最近事件</span></div>
            <div v-if="watchEvents.length" class="event-preview"><strong>{{ watchEvents[0].type }}</strong><span>{{ watchEvents[0].message }}</span><small>{{ formatTime(watchEvents[0].timestamp) }}</small></div><span v-else class="empty-copy">暂无监控事件</span>
            <el-button class="event-link" link type="primary" @click="handleEvents(selectedFolder)">查看全部</el-button>
          </article>
          <article class="detail-card">
            <div class="detail-title"><el-icon><CircleCheck /></el-icon><span>处理规则</span></div>
            <dl><div><dt>转换规则</dt><dd>{{ selectedProfiles.length }} 条</dd></div><div><dt>复制规则</dt><dd>{{ selectedFolder.targets.filter(target => target.type === 'copy').length }} 条</dd></div><div><dt>最近扫描</dt><dd>{{ selectedFolder.lastScanCount }} 个文件</dd></div></dl>
          </article>
        </div>
        <div class="danger-row"><el-button type="danger" link @click="handleDelete(selectedFolder.id)"><el-icon><Delete /></el-icon>删除监控目录</el-button></div>
      </el-dialog>
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
          <template #label>输入目录<el-tooltip content="需要持续扫描和监听的音乐源目录，请选择 Windows 本地或网络目录。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="newFolder.inputDir" placeholder="D:\Music\source" />
        </el-form-item>

        <el-form-item class="form-item-full">
          <template #label>输出目录<el-tooltip content="转换成品保存的位置；建议与 Apple Music 自动导入目录分开。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="newFolder.outputDir" placeholder="D:\Music\output" />
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
          <template #label>输入目录<el-tooltip content="需要持续扫描和监听的音乐源目录，请选择 Windows 本地或网络目录。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="editFolder.inputDir" placeholder="D:\Music\source" />
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
.page-header { padding:30px 34px; margin-bottom:18px; border:1px solid #ece8fb; border-radius:24px; background:linear-gradient(120deg,#fff 40%,#f7f3ff); }

.watch-summary { display: grid; grid-template-columns: repeat(4, 1fr); margin-bottom: 16px; overflow: hidden; background: #fff; border: 1px solid #e7ece9; border-radius: 14px; }
.watch-summary > div { display: flex; align-items: center; justify-content: space-between; padding: 17px 22px; border-right: 1px solid #edf0ef; }
.watch-summary > div:last-child { border-right: 0; }
.watch-summary span { color: #7f8a86; font-size: 12px; }
.watch-summary strong { color: #26332e; font-size: 23px; }
.watch-summary .success-value { color: #0c9c68; }
.watch-summary .danger-value { color: #e45656; }
.watch-workspace { min-height: 620px; overflow: hidden; background: #fff; border: 1px solid #e7ece9; border-radius: 16px; box-shadow: 0 12px 36px rgba(18, 58, 45, .05); }
.watch-table-panel { min-width: 0; }
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

:deep(.watch-details-dialog) { max-width: calc(100vw - 24px); }

@media (max-width: 700px) {
  .watch-summary { grid-template-columns: repeat(2, 1fr); }
  .watch-table-panel { border-right: 0; border-bottom: 1px solid #e7ece9; }
  .watch-folder-form {
    grid-template-columns: 1fr;
  }
}
:global(.watch-details-dialog),:global(.watch-editor-dialog) { max-width:calc(100vw - 24px); margin-top:3vh !important; }
:global(.watch-details-dialog) { position:fixed; top:50%; left:50%; width:min(1180px, calc(100vw - 32px)) !important; margin:0 !important; transform:translate(-50%,-50%); }
:global(.watch-details-dialog .el-dialog__body),:global(.watch-editor-dialog .el-dialog__body) { max-height:calc(94vh - 120px); overflow-y:auto; }
@media (min-width:701px) { :global(.watch-details-dialog .el-dialog__body) { max-height:none; overflow:visible; } }
.watch-details-dialog .inspector-header { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; padding-bottom:22px; border-bottom:1px solid #edf0ef; }
.watch-details-dialog .eyebrow { margin-bottom:6px; color:#0c9c68; font-size:11px; font-weight:800; letter-spacing:.12em; }
.watch-details-dialog .inspector-header h2 { margin:0; color:#1d2925; font-size:24px; }
.watch-details-dialog .inspector-header p { margin:7px 0 0; color:#89948f; font-size:13px; }
.watch-details-dialog .inspector-actions { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:8px; }
.watch-details-dialog .detail-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; padding-top:20px; }
.watch-details-dialog .detail-card { min-width:0; padding:18px; background:#fbfcfc; border:1px solid #e9eeeb; border-radius:13px; }
.watch-details-dialog .wide-card { grid-column:1 / -1; }
.watch-details-dialog .detail-title { display:flex; align-items:center; gap:8px; margin-bottom:14px; color:#25332e; font-size:14px; font-weight:700; }
.watch-details-dialog .detail-title .el-icon { color:#0c9c68; font-size:17px; }
.watch-details-dialog dl { margin:0; }
.watch-details-dialog dl > div { display:flex; align-items:center; justify-content:space-between; gap:16px; min-height:32px; border-bottom:1px dashed #e3e8e5; }
.watch-details-dialog dl > div:last-child { border-bottom:0; }
.watch-details-dialog dt { color:#87918d; font-size:12px; }
.watch-details-dialog dd { max-width:70%; margin:0; overflow:hidden; color:#2f3b37; font-size:13px; font-weight:600; text-align:right; text-overflow:ellipsis; white-space:nowrap; }
.watch-details-dialog code { padding:4px 7px; background:#edf3f0; color:#385148; border-radius:5px; font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:11px; }
.watch-details-dialog .profile-chips { display:flex; flex-wrap:wrap; gap:6px; min-height:32px; align-items:center; }
.event-preview { display:flex; min-height:54px; flex-direction:column; gap:4px; }
.event-preview strong,.event-preview span,.event-preview small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.event-preview strong { color:#53605b; font-size:11px; text-transform:uppercase; }
.event-preview span { color:#35423d; font-size:12px; }
.event-preview small { color:#9ba49f; font-size:10px; }
.event-link { margin-top:8px; padding-left:0; }
.watch-details-dialog .danger-row { display:flex; justify-content:flex-end; padding-top:14px; }
.watch-list-head,.watch-list-item { display:grid; grid-template-columns:minmax(240px,1fr) 220px 210px 260px; gap:16px; align-items:center; }.watch-list-head { padding:0 16px 10px; color:#8b96aa; font-size:12px; font-weight:700; }.watch-list-item { min-height:82px; padding:14px 16px; margin:8px 0; border:1px solid #eee8ff; border-radius:14px; background:#fcfbff; }.watch-list-item:hover { border-color:#cfbfff; background:#fff; box-shadow:0 6px 18px rgba(128,93,218,.08); }.target-copy { display:block; margin-top:7px; color:#8b96aa; font-size:11px; }.watch-row-actions { display:flex; justify-content:flex-end; gap:4px; }.watch-table-panel { padding-bottom:18px; } @media(max-width:700px){:global(.watch-details-dialog){position:relative;top:auto;left:auto;margin:3vh auto !important;transform:none}.watch-details-dialog .inspector-header{flex-direction:column}.watch-details-dialog .detail-grid{grid-template-columns:1fr}.watch-details-dialog .wide-card{grid-column:auto}.watch-details-dialog .inspector-actions{justify-content:flex-start}.watch-list-head{display:none}.watch-list-item{grid-template-columns:1fr auto;gap:10px;padding:15px}.watch-list-item>div:nth-child(2){grid-column:1}.watch-list-item>div:nth-child(3){grid-column:2;grid-row:2;text-align:right}.watch-row-actions{grid-column:1/-1;justify-content:flex-end;border-top:1px solid #eee8ff;padding-top:8px}}
</style>
