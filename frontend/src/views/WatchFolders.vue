<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { WatchFolder, WatchFolderEvent } from '../types'

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
  outputDir: '/mnt/d/Music/output',
})

const editFolder = ref({
  name: '',
  inputDir: '',
  profileIds: [] as string[],
  autoProcess: true,
  recursiveScan: true,
  outputDir: '',
})

onMounted(async () => {
  await Promise.all([store.fetchWatchFolders(), store.fetchProfiles()])
  refreshTimer = setInterval(() => store.fetchWatchFolders(true), 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

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
  <div class="watch-folders-page">
    <div class="page-header">
      <h1>监控目录</h1>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        添加目录
      </el-button>
    </div>

    <!-- 监控目录列表 -->
    <el-card v-loading="store.loading">
      <el-table :data="store.watchFolders" style="width: 100%">
        <el-table-column prop="name" label="名称" min-width="150" />

        <el-table-column prop="inputDir" label="输入目录" min-width="200" />

        <el-table-column prop="outputDir" label="输出目录" min-width="200">
          <template #default="{ row }">
            {{ row.outputDir || '使用配置或全局默认目录' }}
          </template>
        </el-table-column>

        <el-table-column label="转换配置" width="150">
          <template #default="{ row }">
            {{ row.profileIds?.length }} 个配置
          </template>
        </el-table-column>

        <el-table-column prop="autoProcess" label="自动处理" width="100">
          <template #default="{ row }">
            <el-tag :type="row.autoProcess ? 'success' : 'info'" size="small">
              {{ row.autoProcess ? '开启' : '关闭' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="recursiveScan" label="递归扫描" width="100">
          <template #default="{ row }">
            <el-tag :type="row.recursiveScan ? 'success' : 'info'" size="small">
              {{ row.recursiveScan ? '开启' : '关闭' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="实时状态" min-width="180">
          <template #default="{ row }">
            <div class="watch-status">
              <el-tag :type="!row.enabled ? 'info' : row.watching ? 'success' : 'danger'" size="small">
                {{ !row.enabled ? '已停用' : row.watching ? '监听中' : '未监听' }}
              </el-tag>
              <span v-if="row.lastError" class="status-error">{{ row.lastError }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="operation-buttons">
              <el-button type="success" link size="small" @click="handleTriggerConvert(row.id)">
                立即转换
              </el-button>
              <el-button type="primary" link size="small" @click="handleScan(row.id)">
                扫描
              </el-button>
              <el-button type="warning" link size="small" @click="handleEdit(row)">
                编辑
              </el-button>
              <el-button type="info" link size="small" @click="handleEvents(row)">
                事件
              </el-button>
              <el-button :type="row.enabled ? 'info' : 'success'" link size="small" @click="handleToggle(row)">
                {{ row.enabled ? '停用' : '启用' }}
              </el-button>
              <el-button type="danger" link size="small" @click="handleDelete(row.id)">
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建对话框 -->
    <el-dialog
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
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

h1 {
  margin: 0;
  color: #303133;
}

.watch-status {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  font-size: 12px;
  color: #606266;
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
  color: #409eff;
  border-left: 3px solid #409eff;
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

@media (max-width: 700px) {
  .watch-folder-form {
    grid-template-columns: 1fr;
  }
}
</style>
