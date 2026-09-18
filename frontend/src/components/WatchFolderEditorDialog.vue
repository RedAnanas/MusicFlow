<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DeliveryTarget, Profile, WatchFolder } from '../types'
import ServerFileBrowser from './ServerFileBrowser.vue'

export interface WatchFolderEditorForm { name: string; inputDir: string; targets: DeliveryTarget[]; autoProcess: boolean; recursiveScan: boolean; scanIntervalMinutes: number }
const props = defineProps<{ modelValue: boolean; mode: 'create' | 'edit'; form: WatchFolderEditorForm; profiles: Profile[]; folder?: WatchFolder | null; fileStableSeconds: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; submit: [] }>()
const showDirectoryBrowser = ref(false)
const outputIndex = ref<number | null>(null)
const isAbsolutePath = (value: string) => value.startsWith('/') || /^[A-Za-z]:[\\/]/.test(value) || value.startsWith('\\\\')
const isValid = computed(() => props.form.name.trim() && isAbsolutePath(props.form.inputDir) && props.form.targets.length > 0 && props.form.targets.every(target => isAbsolutePath(target.outputDir) && (target.type === 'copy' || Boolean(target.profileId))))
const addRule = () => props.form.targets.push({ type: 'convert', profileId: '', outputDir: '' })
const removeRule = (index: number) => props.form.targets.splice(index, 1)
const selectDirectory = (paths: string[]) => { const path = paths[0] || ''; if (outputIndex.value === null) props.form.inputDir = path; else props.form.targets[outputIndex.value].outputDir = path }
</script>

<template>
  <el-dialog :model-value="modelValue" :title="mode === 'create' ? '添加监控目录' : '编辑监控目录'" width="880px" class="workspace-dialog watch-editor-dialog" destroy-on-close @update:model-value="emit('update:modelValue', $event)">
    <div class="editor-layout"><el-form :model="form" label-position="top" class="editor-form">
      <section><div class="section-heading"><div><span>01</span><h3>基本信息</h3></div><p>为监控目录设置清晰的名称和下载入口。</p></div><div class="two-column"><el-form-item label="名称" required><el-input v-model="form.name" placeholder="例如：无损音乐下载" /></el-form-item><el-form-item label="下载目录" required><el-input v-model="form.inputDir" readonly placeholder="请选择下载目录"><template #append><el-button @click="outputIndex = null; showDirectoryBrowser = true">选择</el-button></template></el-input></el-form-item></div><div class="form-callout"><el-icon><InfoFilled /></el-icon><span>目录中的音乐会按下方规则自动转换或原样复制。</span></div></section>
      <section><div class="section-heading"><div><span>02</span><h3>输出规则</h3></div><p>可并行执行转换输出和原样复制；同名文件会安全跳过。</p></div><div class="rule-list"><article v-for="(target, index) in form.targets" :key="index" class="rule-card"><header><strong>规则 {{ index + 1 }}</strong><el-button link type="danger" @click="removeRule(index)">删除</el-button></header><div class="rule-fields"><el-form-item label="处理方式"><el-radio-group v-model="target.type"><el-radio value="convert">转换输出</el-radio><el-radio value="copy">原样复制</el-radio></el-radio-group></el-form-item><el-form-item v-if="target.type === 'convert'" label="转换方案" required><el-select v-model="target.profileId" placeholder="请选择转换方案"><el-option v-for="profile in profiles" :key="profile.id" :label="profile.name" :value="profile.id" /></el-select></el-form-item><el-form-item label="输出目录" required><el-input v-model="target.outputDir" readonly placeholder="请选择输出目录"><template #append><el-button @click="outputIndex = index; showDirectoryBrowser = true">选择</el-button></template></el-input></el-form-item></div></article><el-button plain class="add-rule" @click="addRule"><el-icon><Plus /></el-icon>添加输出规则</el-button></div></section>
      <section><div class="section-heading"><div><span>03</span><h3>自动处理</h3></div><p>文件稳定后按上方全部规则执行。</p></div><div class="settings-grid"><div class="switch-card"><div><strong>自动处理新文件</strong><small>稳定后自动创建转换或复制任务</small></div><el-switch v-model="form.autoProcess" /></div><div class="switch-card"><div><strong>递归扫描子目录</strong><small>包含下载目录中的所有子文件夹</small></div><el-switch v-model="form.recursiveScan" /></div><el-form-item label="扫描间隔"><el-select v-model="form.scanIntervalMinutes"><el-option label="每 1 分钟" :value="1" /><el-option label="每 5 分钟" :value="5" /><el-option label="每 15 分钟" :value="15" /><el-option label="每 30 分钟" :value="30" /><el-option label="每 60 分钟" :value="60" /></el-select></el-form-item><div class="quality-summary"><span>文件稳定等待</span><strong>{{ fileStableSeconds }} 秒</strong></div></div></section>
    </el-form></div>
    <ServerFileBrowser v-model="showDirectoryBrowser" mode="directory" @select="selectDirectory" />
    <template #footer><div class="dialog-footer"><span>{{ isValid ? `将执行 ${form.targets.length} 条输出规则` : '请补全下载目录和输出规则' }}</span><div><el-button @click="emit('update:modelValue', false)">取消</el-button><el-button type="primary" :disabled="!isValid" @click="emit('submit')">{{ mode === 'create' ? '添加监控目录' : '保存更改' }}</el-button></div></div></template>
  </el-dialog>
</template>

<style scoped>
:global(.watch-editor-dialog) { max-width:calc(100vw - 24px); margin-top:3vh !important; }
:global(.watch-editor-dialog .el-dialog__body) { width:auto; padding:0; max-height:calc(94vh - 120px); overflow-y:auto; }
.editor-layout { min-height:auto; }
.editor-form { max-width:980px; padding:28px 34px; margin:0 auto; }
.editor-form section { width:100%; padding:20px; margin-bottom:16px; border:1px solid #eee8ff; border-radius:14px; background:#fcfbff; }
.section-heading { padding-bottom:12px; margin-bottom:16px; border-bottom:1px solid #eee9f7; }
.section-heading>div { display:flex; align-items:center; gap:9px; }
.section-heading span { color:#8761df; font-size:11px; font-weight:800; }
.section-heading h3 { margin:0; color:#28354d; font-size:18px; }
.section-heading p { margin:7px 0 0; color:#8b96aa; font-size:12px; }
.two-column,.rule-fields,.settings-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
.editor-form :deep(.el-select) { width:100%; }
.form-callout,.quality-summary { display:flex; align-items:center; gap:9px; padding:13px; color:#61716a; background:#f2f6f4; border-radius:9px; font-size:11px; }
.form-callout .el-icon { color:#0c9c68; }
.quality-summary { justify-content:space-between; }
.quality-summary strong { color:#26342e; }
.rule-list { display:flex; flex-direction:column; gap:12px; }
.rule-card { padding:16px; border:1px solid #eee9f7; border-radius:12px; background:#fff; }
.rule-card header { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; color:#43506a; }
.rule-fields :deep(.el-form-item) { margin-bottom:0; }
.add-rule { align-self:flex-start; }
.switch-card { display:flex; align-items:flex-start; justify-content:space-between; padding:15px; background:#f7f9f8; border-radius:10px; }
.switch-card>div { display:flex; flex-direction:column; gap:5px; }
.switch-card small { color:#87928d; font-size:11px; }
.dialog-footer { display:flex; align-items:center; justify-content:space-between; }
.dialog-footer>span { color:#8d9793; font-size:11px; }
html.dark .editor-form section { background:#293142; border-color:#465066; }
html.dark .section-heading, html.dark .rule-card { border-color:#465066; }
html.dark .section-heading h3, html.dark .rule-card header { color:#f0f3f8; }
html.dark .section-heading p, html.dark .switch-card small, html.dark .dialog-footer>span { color:#aeb8c9; }
html.dark .form-callout, html.dark .quality-summary { color:#b8d8ca; background:#20342e; }
html.dark .quality-summary strong { color:#f0f3f8; }
html.dark .rule-card, html.dark .switch-card { background:#252b39; }
@media(max-width:700px){.editor-form{padding:24px}.two-column,.rule-fields,.settings-grid{grid-template-columns:1fr}.dialog-footer>span{display:none}}
</style>
