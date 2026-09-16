<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { DeliveryTarget, Profile, WatchFolder } from '../types'
import ServerFileBrowser from './ServerFileBrowser.vue'

export interface WatchFolderEditorForm {
  name: string
  inputDir: string
  targets: DeliveryTarget[]
  autoProcess: boolean
  recursiveScan: boolean
  scanIntervalMinutes: number
}

const props = defineProps<{ modelValue: boolean; mode: 'create' | 'edit'; form: WatchFolderEditorForm; profiles: Profile[]; folder?: WatchFolder | null; fileStableSeconds: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; submit: [] }>()
const openSections = ref<string[]>([])
const showDirectoryBrowser = ref(false)
const outputIndex = ref<number | null>(null)

watch(() => props.modelValue, visible => {
  if (visible) openSections.value = [props.mode === 'create' ? 'directory' : 'targets']
})

const isAbsolutePath = (value: string) => value.startsWith('/') || /^[A-Za-z]:[\\/]/.test(value) || value.startsWith('\\\\')
const isValid = computed(() => props.form.name.trim() && isAbsolutePath(props.form.inputDir) && props.form.targets.length > 0 && props.form.targets.every(target => isAbsolutePath(target.outputDir) && (target.type === 'copy' || Boolean(target.profileId))))
const ruleName = (target: DeliveryTarget) => target.type === 'convert' ? '转换输出' : '原样复制'

const addRule = () => props.form.targets.push({ type: 'convert', profileId: '', outputDir: '' })
const removeRule = (index: number) => props.form.targets.splice(index, 1)
const openDirectoryBrowser = (index: number) => {
  outputIndex.value = index
  showDirectoryBrowser.value = true
}
const selectDirectory = (paths: string[]) => {
  const selectedPath = paths[0] || ''
  if (outputIndex.value === null) {
    props.form.inputDir = selectedPath
    return
  }
  props.form.targets[outputIndex.value].outputDir = selectedPath
}
</script>

<template>
  <el-dialog :model-value="modelValue" :title="mode === 'create' ? '添加监控目录' : '编辑监控目录'" width="1000px" class="workspace-dialog watch-editor-dialog" destroy-on-close @update:model-value="emit('update:modelValue', $event)">
    <div class="watch-editor-layout">
      <main class="watch-editor-main">
        <header class="watch-editor-header"><div class="folder-symbol"><el-icon><FolderOpened /></el-icon></div><div><span>{{ mode === 'create' ? '创建新的下载入口' : '更新下载入口规则' }}</span><h3>{{ form.name || '未命名监控目录' }}</h3></div><el-tag v-if="mode === 'edit'" :type="folder?.watching ? 'success' : 'info'" effect="light">{{ folder?.watching ? '监听中' : '未监听' }}</el-tag></header>
        <el-collapse v-model="openSections" class="rule-sections">
          <el-collapse-item name="directory"><template #title><div class="rule-title"><strong>下载入口</strong><small>下载器保存到此目录的文件将按输出规则处理</small></div></template><el-form :model="form" label-position="top" class="rule-form"><el-form-item label="名称" required><el-input v-model="form.name" placeholder="例如：无损音乐下载" /></el-form-item><el-form-item label="下载目录" required><el-input v-model="form.inputDir" readonly placeholder="请选择下载器保存到的目录"><template #append><el-button @click="outputIndex = null; showDirectoryBrowser = true"><el-icon><FolderOpened /></el-icon>选择</el-button></template></el-input></el-form-item></el-form></el-collapse-item>
          <el-collapse-item name="targets"><template #title><div class="rule-title"><strong>输出规则</strong><small>可添加多条规则，同一文件会并行处理</small></div></template><div class="rule-list"><section v-for="(target, index) in form.targets" :key="index" class="rule-card"><div class="rule-card-head"><strong>规则 {{ index + 1 }} · {{ ruleName(target) }}</strong><el-button link type="danger" @click="removeRule(index)">删除</el-button></div><el-form label-position="top" class="target-form"><el-form-item label="处理方式"><el-radio-group v-model="target.type"><el-radio value="convert">转换输出</el-radio><el-radio value="copy">原样复制</el-radio></el-radio-group></el-form-item><el-form-item v-if="target.type === 'convert'" label="转换方案" required><el-select v-model="target.profileId" placeholder="请选择转换方案"><el-option v-for="profile in profiles" :key="profile.id" :label="profile.name" :value="profile.id" /></el-select></el-form-item><el-form-item label="输出目录" required><el-input v-model="target.outputDir" readonly placeholder="请选择文件输出目录"><template #append><el-button @click="openDirectoryBrowser(index)">选择</el-button></template></el-input><small>{{ target.type === 'copy' ? '保留原文件格式、标签和目录结构。' : '按所选方案转换后输出。' }}</small></el-form-item></el-form></section><el-button plain class="add-rule" @click="addRule"><el-icon><Plus /></el-icon>添加输出规则</el-button></div></el-collapse-item>
          <el-collapse-item name="rules"><template #title><div class="rule-title"><strong>自动处理规则</strong><small>稳定文件才会开始处理</small></div></template><div class="rule-grid"><div class="switch-setting"><div><strong>自动处理新文件</strong><span>文件稳定后自动执行全部输出规则</span></div><el-switch v-model="form.autoProcess" /></div><div class="switch-setting"><div><strong>递归扫描子目录</strong><span>包含下载目录内的子文件夹</span></div><el-switch v-model="form.recursiveScan" /></div><el-form label-position="top"><el-form-item label="扫描间隔"><el-select v-model="form.scanIntervalMinutes"><el-option label="每 1 分钟" :value="1" /><el-option label="每 5 分钟" :value="5" /><el-option label="每 15 分钟" :value="15" /><el-option label="每 30 分钟" :value="30" /><el-option label="每 60 分钟" :value="60" /></el-select></el-form-item></el-form><div class="readonly-setting"><span>文件稳定等待</span><strong>{{ fileStableSeconds }} 秒</strong><small>避免复制或转换尚未写完的文件</small></div></div></el-collapse-item>
        </el-collapse>
      </main>
      <aside class="impact-rail"><span class="rail-eyebrow">保存前检查</span><div class="check-state" :class="{ valid: isValid }"><el-icon><CircleCheckFilled v-if="isValid" /><WarningFilled v-else /></el-icon><div><strong>{{ isValid ? '配置完整' : '需要补充信息' }}</strong><span>{{ isValid ? `将并行执行 ${form.targets.length} 条输出规则` : '请检查下载目录和输出规则' }}</span></div></div><section><h4>安全行为</h4><p>保留原下载文件</p><p>原样复制写入完成后才显示</p><p>同名文件不覆盖，记录跳过事件</p></section></aside>
    </div>
    <ServerFileBrowser v-model="showDirectoryBrowser" mode="directory" @select="selectDirectory" />
    <template #footer><div class="dialog-footer"><span>每个下载入口可按需配置一条或多条输出规则</span><div><el-button @click="emit('update:modelValue', false)">取消</el-button><el-button type="primary" :disabled="!isValid" @click="emit('submit')">{{ mode === 'create' ? '添加监控目录' : '保存更改' }}</el-button></div></div></template>
  </el-dialog>
</template>

<style scoped>
:global(.watch-editor-dialog) { max-width: calc(100vw - 48px); margin-top: 3vh !important; }:global(.watch-editor-dialog .el-dialog__body) { width: auto; padding: 0; overflow: hidden; }.watch-editor-layout { display: grid; grid-template-columns: minmax(0, 1fr) 260px; min-height: 550px; overflow: hidden; }.watch-editor-main { min-width: 0; padding: 20px 24px; }.watch-editor-header { display: flex; align-items: center; gap: 13px; }.folder-symbol { display: grid; width: 44px; height: 44px; place-items: center; color: #0c9c68; background: #e5f4ef; border-radius: 11px; font-size: 20px; }.watch-editor-header > div:nth-child(2) { flex: 1; }.watch-editor-header span { color: #84908b; font-size: 10px; }.watch-editor-header h3 { margin: 3px 0 0; color: #26342e; font-size: 19px; }.rule-sections { margin-top: 16px; border-top: 0; }.rule-sections :deep(.el-collapse-item__header) { height: 52px; border: 1px solid #e5ebe8; border-radius: 10px; padding: 0 14px; margin-top: 8px; }.rule-sections :deep(.el-collapse-item__wrap) { border: 0; }.rule-sections :deep(.el-collapse-item__content) { padding: 12px 12px 0; }.rule-title { display: flex; align-items: center; flex: 1; }.rule-title strong { color: #087955; font-size: 13px; }.rule-title small { margin-left: auto; color: #98a19d; font-size: 10px; }.rule-form, .target-form { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }.rule-form :deep(.el-form-item), .target-form :deep(.el-form-item) { margin-bottom: 8px; }.target-form :deep(.el-select) { width: 100%; }.target-form small { display: block; margin-top: 5px; color: #84908b; font-size: 10px; }.rule-list { display: flex; flex-direction: column; gap: 10px; }.rule-card { padding: 14px; background: #f7f9f8; border: 1px solid #e6ece9; border-radius: 10px; }.rule-card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; color: #314039; font-size: 12px; }.add-rule { align-self: flex-start; }.rule-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 18px; }.switch-setting { display: flex; align-items: flex-start; justify-content: space-between; padding: 12px; background: #f7f9f8; border-radius: 9px; }.switch-setting > div { display: flex; flex-direction: column; gap: 4px; }.switch-setting strong { font-size: 11px; }.switch-setting span, .readonly-setting small { color: #8d9793; font-size: 9px; }.readonly-setting { display: grid; grid-template-columns: 1fr auto; gap: 5px; padding: 9px 12px; background: #f7f9f8; border-radius: 9px; font-size: 10px; }.readonly-setting small { grid-column: 1 / -1; }.impact-rail { padding: 20px 18px; background: #fbfcfc; border-left: 1px solid #e7ece9; }.rail-eyebrow { color: #0c9c68; font-size: 10px; font-weight: 800; letter-spacing: .1em; }.check-state { display: flex; gap: 9px; padding: 11px; margin: 11px 0 16px; color: #b87818; background: #fff7e8; border-radius: 9px; }.check-state.valid { color: #087955; background: #e8f5f0; }.check-state > div { display: flex; flex-direction: column; gap: 3px; }.check-state strong { color: #36443e; font-size: 11px; }.check-state span, .impact-rail p { color: #66736e; font-size: 10px; }.impact-rail section { padding: 12px 0; border-top: 1px solid #e7ebe9; }.impact-rail h4 { margin: 0 0 9px; color: #53605b; font-size: 11px; }.dialog-footer { display: flex; align-items: center; justify-content: space-between; }.dialog-footer > span { color: #8d9793; font-size: 11px; }@media (max-width: 850px) { .watch-editor-layout { grid-template-columns: 1fr; }.impact-rail { display: none; }.rule-form, .target-form, .rule-grid { grid-template-columns: 1fr; }.rule-title small { display: none; } }
</style>
