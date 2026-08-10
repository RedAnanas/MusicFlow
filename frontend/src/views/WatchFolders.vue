<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { WatchFolder } from '../types'

const store = useAppStore()
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const selectedFolder = ref<WatchFolder | null>(null)

const newFolder = ref({
  name: '',
  inputDir: '',
  profileIds: [] as string[],
  autoProcess: true,
  recursiveScan: true,
  scanIntervalMinutes: 5,
})

const editFolder = ref({
  name: '',
  inputDir: '',
  profileIds: [] as string[],
  autoProcess: true,
  recursiveScan: true,
  scanIntervalMinutes: 5,
})

onMounted(() => {
  store.fetchWatchFolders()
  store.fetchProfiles()
})

const handleCreate = async () => {
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
    }
  } catch (error) {
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
  }
  showEditDialog.value = true
}

const handleUpdate = async () => {
  if (!selectedFolder.value) return
  try {
    await store.updateWatchFolder(selectedFolder.value.id, editFolder.value)
    ElMessage.success('监控目录更新成功')
    showEditDialog.value = false
  } catch (error) {
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
    // 先扫描目录
    const scanResult = await store.scanWatchFolder(folderId)

    if (!scanResult.files || scanResult.files.length === 0) {
      ElMessage.warning('目录中没有找到音频文件')
      return
    }

    // 为每个文件创建转换任务
    let taskCount = 0
    for (const filePath of scanResult.files) {
      // 获取文件名
      const fileName = filePath.split(/[/\\]/).pop() || ''
      const fileExt = fileName.split('.').pop() || ''
      const outputFile = filePath.replace('.' + fileExt, '.m4a')

      // 创建转换任务
      try {
        await fetch('http://localhost:8082/api/tasks/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_file: filePath,
            output_file: outputFile,
            profile_id: store.profiles[0]?.id || 'apple-music-aac-256'
          })
        })
        taskCount++
      } catch (err) {
        console.error('Failed to create task:', err)
      }
    }

    ElMessage.success(`已创建 ${taskCount} 个转换任务`)
  } catch (error) {
    ElMessage.error('触发转换失败')
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

        <el-table-column label="输出配置" width="150">
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

        <el-table-column prop="scanIntervalMinutes" label="扫描间隔" width="100">
          <template #default="{ row }">
            {{ row.scanIntervalMinutes }} 分钟
          </template>
        </el-table-column>

        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button type="success" link size="small" @click="handleTriggerConvert(row.id)">
              立即转换
            </el-button>
            <el-button type="primary" link size="small" @click="handleScan(row.id)">
              扫描
            </el-button>
            <el-button type="warning" link size="small" @click="handleEdit(row)">
              编辑
            </el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row.id)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      title="添加监控目录"
      width="600px"
    >
      <el-form :model="newFolder" label-width="120px">
        <el-form-item label="名称">
          <el-input v-model="newFolder.name" placeholder="例如：下载音乐" />
        </el-form-item>

        <el-form-item label="输入目录">
          <el-input v-model="newFolder.inputDir" placeholder="/music/source" />
        </el-form-item>

        <el-form-item label="输出配置">
          <el-select v-model="newFolder.profileIds" multiple placeholder="选择 Profile">
            <el-option
              v-for="profile in store.profiles"
              :key="profile.id"
              :label="profile.name"
              :value="profile.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="自动处理">
          <el-switch v-model="newFolder.autoProcess" />
        </el-form-item>

        <el-form-item label="递归扫描">
          <el-switch v-model="newFolder.recursiveScan" />
        </el-form-item>

        <el-form-item label="扫描间隔">
          <el-select v-model="newFolder.scanIntervalMinutes">
            <el-option label="每 5 分钟" :value="5" />
            <el-option label="每 15 分钟" :value="15" />
            <el-option label="每 30 分钟" :value="30" />
            <el-option label="每小时" :value="60" />
          </el-select>
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
      width="600px"
    >
      <el-form :model="editFolder" label-width="120px">
        <el-form-item label="名称">
          <el-input v-model="editFolder.name" placeholder="例如：下载音乐" />
        </el-form-item>

        <el-form-item label="输入目录">
          <el-input v-model="editFolder.inputDir" placeholder="/music/source" />
        </el-form-item>

        <el-form-item label="输出配置">
          <el-select v-model="editFolder.profileIds" multiple placeholder="选择 Profile">
            <el-option
              v-for="profile in store.profiles"
              :key="profile.id"
              :label="profile.name"
              :value="profile.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="自动处理">
          <el-switch v-model="editFolder.autoProcess" />
        </el-form-item>

        <el-form-item label="递归扫描">
          <el-switch v-model="editFolder.recursiveScan" />
        </el-form-item>

        <el-form-item label="扫描间隔">
          <el-select v-model="editFolder.scanIntervalMinutes">
            <el-option label="每 5 分钟" :value="5" />
            <el-option label="每 15 分钟" :value="15" />
            <el-option label="每 30 分钟" :value="30" />
            <el-option label="每小时" :value="60" />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUpdate">更新</el-button>
      </template>
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
</style>
