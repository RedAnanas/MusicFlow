<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAppStore } from '../stores/app'
import type { WatchFolder } from '../types'

const store = useAppStore()
const showCreateDialog = ref(false)

const newFolder = ref({
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
    // API 调用
    ElMessage.success('监控目录创建成功')
    showCreateDialog.value = false
  } catch (error) {
    ElMessage.error('创建失败')
  }
}

const handleScan = async (folderId: string) => {
  try {
    ElMessage.success('开始扫描')
  } catch (error) {
    ElMessage.error('扫描失败')
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

        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleScan(row.id)">
              立即扫描
            </el-button>
            <el-button type="danger" link size="small">
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
