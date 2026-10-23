<script setup lang="ts">
import { ref } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '../stores/app'

interface Preview {
  app_version: string
  platform: string
  current_revision: string
  counts: Record<string, number>
  paths: { path: string; available: boolean }[]
}
const emit = defineEmits<{ imported: [] }>()
const store = useAppStore()
const selected = ref<File | null>(null)
const preview = ref<Preview | null>(null)
const busy = ref(false)
const error = ref('')
const result = ref<{ backup_id: string; message: string } | null>(null)

async function selectFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  selected.value = null
  preview.value = null
  error.value = ''
  result.value = null
  if (!file) return
  if (file.size > 1024 * 1024) { error.value = '配置文件不能超过 1 MiB'; return }
  busy.value = true
  try {
    const data = new FormData()
    data.append('file', file)
    preview.value = (await axios.post('/api/system/configuration/preview', data)).data
    selected.value = file
  } catch (failure: any) { error.value = failure.response?.data?.detail || '配置预览失败' }
  finally { busy.value = false }
}

async function restore() {
  if (!selected.value || !preview.value) return
  try {
    await ElMessageBox.confirm('将替换当前音乐路径、转换方案、监控与投递规则、双库关联和 musicdl 地址。系统会先备份原配置，导入的监控全部停用。确认继续？', '确认恢复配置', { type: 'warning', confirmButtonText: '备份当前配置并恢复', cancelButtonText: '取消' })
  } catch { return }
  busy.value = true
  error.value = ''
  try {
    const data = new FormData()
    data.append('file', selected.value)
    data.append('current_revision', preview.value.current_revision)
    result.value = (await axios.post('/api/system/configuration/import', data)).data
    selected.value = null
    preview.value = null
    await Promise.allSettled([store.fetchProfiles(), store.fetchWatchFolders(), store.fetchSettings(), store.fetchLibrarySources()])
    emit('imported')
    ElMessage.success('配置已恢复，导入的监控保持停用')
  } catch (failure: any) { error.value = failure.response?.data?.detail || '恢复失败，请刷新后重新预览' }
  finally { busy.value = false }
}
</script>

<template>
  <section class="configuration-backup" v-loading="busy">
    <h2>配置备份与迁移</h2>
    <p>备份音乐来源、媒体库路径、转换方案、监控与投递规则、通用设置、双库关联和 musicdl 地址。</p>
    <p>不包含歌曲、任务历史、资料库快照、Apple 授权、密钥或算法文件；Docker 挂载和服务令牌需在新环境单独设置。</p>
    <div class="backup-actions"><a href="/api/system/configuration/export" download><el-button type="primary" plain>导出配置</el-button></a><label>选择要恢复的配置 <input type="file" accept=".json,application/json" :disabled="busy" @change="selectFile" /></label></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <div v-if="preview" class="backup-preview">
      <h3>导入预览 · {{ preview.platform }} · MusicFlow {{ preview.app_version }}</h3>
      <div class="backup-actions"><el-tag v-for="(count, label) in preview.counts" :key="label">{{ label }}：{{ count }}</el-tag></div>
      <p>按原路径恢复，不会自动转换 Windows/Linux 路径。不存在的路径需调整配置或容器挂载；导入的监控全部停用，核对后手动启用。</p>
      <el-table v-if="preview.paths.length" :data="preview.paths" max-height="280"><el-table-column prop="path" label="配置中的路径" min-width="240" /><el-table-column label="当前环境" width="150"><template #default="{ row }"><el-tag :type="row.available ? 'success' : 'warning'">{{ row.available ? '可访问' : '未找到 / 不可访问' }}</el-tag></template></el-table-column></el-table>
      <p>恢复前请停用当前全部监控，并等待转换、下载及文件导入任务结束。并发参数重启后生效。</p>
      <el-button type="primary" @click="restore">确认恢复配置…</el-button>
    </div>
    <div v-if="result"><el-alert :title="result.message" type="success" :closable="false" show-icon /><a :href="`/api/system/configuration/backups/${result.backup_id}`" download>下载导入前的配置备份</a></div>
  </section>
</template>

<style scoped>
.configuration-backup { padding: 24px; }
h2 { margin: 0 0 10px; color: var(--mf-text); font-size: 19px; }
h3 { margin: 16px 0; color: var(--mf-text); font-size: 14px; }
p { margin: 8px 0; color: var(--mf-text-muted); font-size: 13px; line-height: 1.75; }
.backup-actions { display: flex; align-items: flex-end; flex-wrap: wrap; gap: 16px; margin: 20px 0 0; }
.backup-actions label { display: grid; min-width: 0; gap: 8px; color: var(--mf-text-muted); font-size: 12px; }
.backup-preview { margin-top: 20px; padding: 18px; border: 1px solid var(--mf-border); border-radius: 14px; background: var(--mf-surface-muted); }
.backup-preview .backup-actions { margin: 12px 0; }
a { display: inline-block; margin: 0; color: var(--el-color-primary); }
input[type=file] { max-width: 100%; min-width: 0; font: inherit; color: var(--mf-text-muted); }
input[type=file]::file-selector-button { padding: 7px 11px; margin-right: 9px; border: 1px solid var(--mf-border); border-radius: 8px; background: var(--mf-surface-muted); color: var(--mf-text); font: inherit; cursor: pointer; }
input[type=file]:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 4px; }
@media (max-width: 760px) { .configuration-backup { padding: 20px; }.backup-actions { align-items: flex-start; flex-direction: column; }.backup-preview { padding: 14px; } }
</style>
