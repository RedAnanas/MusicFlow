<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import type { FileSystemEntry } from '../types'

const props = withDefaults(defineProps<{
  modelValue: boolean
  mode?: 'files' | 'directory'
}>(), {
  mode: 'files',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  select: [paths: string[]]
}>()

const roots = ref<FileSystemEntry[]>([])
const entries = ref<FileSystemEntry[]>([])
const currentPath = ref('')
const parentPath = ref<string | null>(null)
const selectedPaths = ref<string[]>([])
const loading = ref(false)
const truncated = ref(false)

const title = computed(() => props.mode === 'directory' ? '选择服务器文件夹' : '选择服务器文件')
const canConfirm = computed(() => props.mode === 'directory' ? Boolean(currentPath.value) : selectedPaths.value.length > 0)

const loadRoots = async () => {
  loading.value = true
  try {
    const response = await axios.get<FileSystemEntry[]>('/api/filesystem/roots')
    roots.value = response.data
    entries.value = []
    currentPath.value = ''
    parentPath.value = null
  } catch {
    ElMessage.error('读取服务器文件系统入口失败')
  } finally {
    loading.value = false
  }
}

const openDirectory = async (path: string) => {
  loading.value = true
  selectedPaths.value = []
  try {
    const response = await axios.get('/api/filesystem/entries', {
      params: { path, audio_only: true },
    })
    currentPath.value = response.data.path
    parentPath.value = response.data.parent
    entries.value = response.data.entries
    truncated.value = response.data.truncated
  } catch (error) {
    const message = axios.isAxiosError(error) ? error.response?.data?.detail : null
    ElMessage.error(message || '读取目录失败')
  } finally {
    loading.value = false
  }
}

const handleEntryClick = (entry: FileSystemEntry) => {
  if (entry.is_directory) return
  selectedPaths.value = selectedPaths.value.includes(entry.path)
    ? selectedPaths.value.filter(path => path !== entry.path)
    : [...selectedPaths.value, entry.path]
}

const confirm = () => {
  const paths = props.mode === 'directory' ? [currentPath.value] : selectedPaths.value
  emit('select', paths)
  emit('update:modelValue', false)
}

watch(() => props.modelValue, visible => {
  if (visible) {
    selectedPaths.value = []
    loadRoots()
  }
})
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="760px"
    class="server-file-browser"
    append-to-body
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="browser-toolbar">
      <el-button :disabled="!currentPath" @click="loadRoots"><el-icon><HomeFilled /></el-icon>入口</el-button>
      <el-button :disabled="!parentPath" @click="parentPath && openDirectory(parentPath)"><el-icon><Back /></el-icon>上一级</el-button>
      <el-input :model-value="currentPath" readonly placeholder="请选择文件系统入口" />
    </div>

    <div v-loading="loading" class="browser-list">
      <template v-if="!currentPath">
        <button
          v-for="root in roots"
          :key="root.path"
          type="button"
          class="browser-entry"
          @click="openDirectory(root.path)"
        >
          <el-icon><FolderOpened /></el-icon><span>{{ root.name }}</span><small>{{ root.path }}</small>
        </button>
      </template>

      <template v-else>
        <button
          v-for="entry in entries"
          :key="entry.path"
          type="button"
          class="browser-entry"
          :class="{ selected: selectedPaths.includes(entry.path) }"
          @click="entry.is_directory ? openDirectory(entry.path) : handleEntryClick(entry)"
        >
          <el-icon><FolderOpened v-if="entry.is_directory" /><Headset v-else /></el-icon>
          <span>{{ entry.name }}</span>
          <small>{{ entry.is_directory ? '文件夹' : '音频文件' }}</small>
        </button>
      </template>

      <el-empty v-if="currentPath && !loading && !entries.length" description="此目录没有可显示的文件" />
    </div>
    <p v-if="truncated" class="browser-warning">当前目录项目过多，仅显示前 1000 项。</p>

    <template #footer>
      <div class="browser-footer">
        <span>{{ mode === 'directory' ? '将选择当前目录' : `已选择 ${selectedPaths.length} 个文件` }}</span>
        <div><el-button @click="emit('update:modelValue', false)">取消</el-button><el-button type="primary" :disabled="!canConfirm" @click="confirm">确定</el-button></div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.browser-toolbar { display: grid; grid-template-columns: auto auto minmax(0, 1fr); gap: 8px; margin-bottom: 12px; }
.browser-list { min-height: 360px; max-height: 55vh; overflow: auto; border: 1px solid #dfe6e1; border-radius: 9px; }
.browser-entry { display: grid; width: 100%; grid-template-columns: 24px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 11px 14px; color: #34423a; background: #fff; border: 0; border-bottom: 1px solid #edf1ee; text-align: left; cursor: pointer; }
.browser-entry:hover, .browser-entry.selected { background: #eaf6ef; color: #087b56; }
.browser-entry .el-icon { color: #16a06d; font-size: 18px; }
.browser-entry small { color: #929c96; }
.browser-warning { margin: 10px 0 0; color: #b47a20; font-size: 12px; }
.browser-footer { display: flex; align-items: center; justify-content: space-between; color: #7e8a83; font-size: 12px; }
</style>
