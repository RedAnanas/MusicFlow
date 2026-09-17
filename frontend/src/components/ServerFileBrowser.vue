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
:global(.server-file-browser) { display: flex; max-height: calc(100dvh - 32px); flex-direction: column; margin: 16px auto !important; border-radius: 20px; }.server-file-browser :deep(.el-dialog__header), .server-file-browser :deep(.el-dialog__footer) { flex: 0 0 auto; }.server-file-browser :deep(.el-dialog__body) { min-height: 0; overflow: auto; }.server-file-browser :deep(.el-dialog__footer) { border-top: 1px solid #ececf2; }
.browser-toolbar { display: grid; grid-template-columns: auto auto minmax(0, 1fr); gap: 8px; margin-bottom: 14px; }.browser-toolbar :deep(.el-button) { border-radius: 10px; }.browser-toolbar :deep(.el-input__wrapper) { min-height: 38px; background: #fbfcfe; box-shadow: 0 0 0 1px #e3e5ec inset; border-radius: 10px; }
.browser-list { min-height: 360px; max-height: 55vh; overflow: auto; border: 1px solid #ebe8f3; border-radius: 14px; }.browser-entry { display: grid; width: 100%; grid-template-columns: 24px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 13px 15px; color: #4b566b; background: #fff; border: 0; border-bottom: 1px solid #f0eef5; text-align: left; cursor: pointer; }.browser-entry:last-child { border-bottom: 0; }
.browser-entry:hover, .browser-entry.selected { color: #815fd0; background: #f4f0ff; }.browser-entry .el-icon { color: #9a73ee; font-size: 18px; }.browser-entry span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 650; }.browser-entry small { color: #98a0af; }.browser-warning { padding: 10px 12px; margin: 12px 0 0; color: #a2772d; background: #fff8e9; border: 1px solid #f4e2bd; border-radius: 10px; font-size: 12px; }.browser-footer { display: flex; align-items: center; justify-content: space-between; color: #7e8a93; font-size: 12px; }
@media (max-width: 700px) { :global(.server-file-browser) { width: calc(100vw - 24px) !important; max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); margin: 12px auto !important; border-radius: 18px; }.server-file-browser :deep(.el-dialog__header) { padding: 18px 18px 14px; margin-right: 0; }.server-file-browser :deep(.el-dialog__body) { padding: 0 16px; }.server-file-browser :deep(.el-dialog__footer) { padding: 12px 16px calc(12px + env(safe-area-inset-bottom)); }.browser-toolbar { grid-template-columns: 1fr 1fr; }.browser-toolbar :deep(.el-input) { grid-column: 1 / -1; }.browser-list { min-height: 0; max-height: calc(100dvh - 300px); }.browser-entry { grid-template-columns: 22px minmax(0, 1fr); padding: 13px 12px; }.browser-entry small { grid-column: 2; }.browser-footer > span { display: none; }.browser-footer > div { display: flex; width: 100%; gap: 8px; }.browser-footer :deep(.el-button) { flex: 1; margin: 0; } }
</style>
