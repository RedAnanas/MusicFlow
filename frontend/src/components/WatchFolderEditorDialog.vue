<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Profile, WatchFolder } from '../types'

export interface WatchFolderEditorForm {
  name: string
  inputDir: string
  profileIds: string[]
  autoProcess: boolean
  recursiveScan: boolean
  scanIntervalMinutes: number
  outputDir: string
}

const props = defineProps<{ modelValue: boolean; mode: 'create' | 'edit'; form: WatchFolderEditorForm; profiles: Profile[]; folder?: WatchFolder | null; fileStableSeconds: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; submit: [] }>()
const openSections = ref<string[]>([])
watch(() => props.modelValue, visible => {
  if (visible) openSections.value = [props.mode === 'create' ? 'directory' : 'rules']
})

const isWslPath = (value: string) => value.startsWith('/')
const isValid = computed(() => props.form.name.trim() && isWslPath(props.form.inputDir) && props.form.profileIds.length > 0)
const selectedProfiles = computed(() => props.profiles.filter(profile => props.form.profileIds.includes(profile.id)))
const outputPreview = computed(() => props.form.outputDir.trim() || '使用转换方案或全局输出目录')
</script>

<template>
  <el-dialog :model-value="modelValue" :title="mode === 'create' ? '添加监控目录' : '编辑监控目录'" width="1100px" class="workspace-dialog watch-editor-dialog" destroy-on-close @update:model-value="emit('update:modelValue', $event)">
    <div class="watch-editor-layout">
      <main class="watch-editor-main">
        <header class="watch-editor-header">
          <div class="folder-symbol"><el-icon><FolderOpened /></el-icon></div>
          <div><span>{{ mode === 'create' ? '创建新的自动化入口' : '更新监控规则' }}</span><h3>{{ form.name || '未命名监控目录' }}</h3></div>
          <el-tag v-if="mode === 'edit'" :type="folder?.watching ? 'success' : 'info'" effect="light">{{ folder?.watching ? '监听中' : '未监听' }}</el-tag>
        </header>

        <div class="path-flow"><div><span>输入目录（WSL）</span><code>{{ form.inputDir || '尚未设置' }}</code></div><el-icon><Right /></el-icon><div><span>输出目录（WSL）</span><code>{{ outputPreview }}</code></div></div>

        <el-collapse v-model="openSections" class="rule-sections">
          <el-collapse-item name="directory">
            <template #title><div class="rule-title"><span>1</span><strong>监控目录</strong><small>定义目录名称和来源路径</small></div></template>
            <el-form :model="form" label-position="top" class="rule-form"><el-form-item label="名称" required><el-input v-model="form.name" placeholder="例如：下载音乐" /></el-form-item><el-form-item label="输入目录" required :error="form.inputDir && !isWslPath(form.inputDir) ? '请输入以 / 开头的 WSL 绝对路径' : ''"><el-input v-model="form.inputDir" placeholder="/mnt/d/Music/source" /></el-form-item></el-form>
          </el-collapse-item>
          <el-collapse-item name="profiles">
            <template #title><div class="rule-title"><span>2</span><strong>转换方案</strong><small>选择新文件使用的转换规则</small></div></template>
            <el-form label-position="top" class="rule-form"><el-form-item label="关联方案" required><el-select v-model="form.profileIds" multiple placeholder="至少选择一个转换方案"><el-option v-for="profile in profiles" :key="profile.id" :label="profile.name" :value="profile.id"><span>{{ profile.name }}</span><small class="option-meta">{{ profile.outputFormat.toUpperCase() }} · {{ profile.codec?.toUpperCase() }}</small></el-option></el-select></el-form-item></el-form>
          </el-collapse-item>
          <el-collapse-item name="rules">
            <template #title><div class="rule-title"><span>3</span><strong>自动处理规则</strong><small>设置扫描周期和发现文件后的行为</small></div></template>
            <div class="rule-grid"><div class="switch-setting"><div><strong>自动处理新文件</strong><span>文件稳定后自动创建转换任务</span></div><el-switch v-model="form.autoProcess" /></div><div class="switch-setting"><div><strong>递归扫描子目录</strong><span>包含输入目录下的所有层级</span></div><el-switch v-model="form.recursiveScan" /></div><el-form label-position="top"><el-form-item label="扫描间隔"><el-select v-model="form.scanIntervalMinutes"><el-option label="每 1 分钟" :value="1" /><el-option label="每 5 分钟" :value="5" /><el-option label="每 15 分钟" :value="15" /><el-option label="每 30 分钟" :value="30" /><el-option label="每 60 分钟" :value="60" /></el-select></el-form-item></el-form><div class="readonly-setting"><span>文件稳定等待</span><strong>{{ fileStableSeconds }} 秒</strong><small>使用全局设置，避免转换尚未写完的文件</small></div></div>
          </el-collapse-item>
          <el-collapse-item name="output">
            <template #title><div class="rule-title"><span>4</span><strong>输出目录</strong><small>覆盖方案默认目录（可选）</small></div></template>
            <el-form :model="form" label-position="top" class="rule-form"><el-form-item label="自定义输出目录" :error="form.outputDir && !isWslPath(form.outputDir) ? '请输入以 / 开头的 WSL 绝对路径' : ''"><el-input v-model="form.outputDir" clearable placeholder="留空则使用转换方案或全局输出目录" /><span class="path-tip">优先级：监控目录 ＞ 转换方案 ＞ 全局默认目录</span></el-form-item></el-form>
          </el-collapse-item>
        </el-collapse>
      </main>

      <aside class="impact-rail">
        <span class="rail-eyebrow">保存前检查</span>
        <div class="check-state" :class="{ valid: isValid }"><el-icon><CircleCheckFilled v-if="isValid" /><WarningFilled v-else /></el-icon><div><strong>{{ isValid ? '配置完整' : '需要补充信息' }}</strong><span>{{ isValid ? '保存后可正常运行' : '请检查名称、路径和转换方案' }}</span></div></div>
        <section><h4>影响范围</h4><dl><div><dt>转换方案</dt><dd>{{ selectedProfiles.length }} 个</dd></div><div><dt>扫描范围</dt><dd>{{ form.recursiveScan ? '包含子目录' : '仅当前目录' }}</dd></div><div><dt>任务行为</dt><dd>{{ form.autoProcess ? '自动创建' : '仅发现文件' }}</dd></div><div><dt>扫描周期</dt><dd>{{ form.scanIntervalMinutes }} 分钟</dd></div></dl></section>
        <section><h4>已选方案</h4><div class="profile-tags"><el-tag v-for="profile in selectedProfiles" :key="profile.id" effect="plain">{{ profile.name }}</el-tag><span v-if="!selectedProfiles.length">尚未选择转换方案</span></div></section>
        <section v-if="mode === 'edit' && folder?.watching" class="safety-note"><el-icon><Warning /></el-icon><div><strong>目录正在监听</strong><span>保存配置后监听器会按最新规则继续工作，请避免在文件集中写入时修改路径。</span></div></section>
        <section class="behavior-list"><h4>保存后的行为</h4><p><el-icon><CircleCheck /></el-icon>持续检测新加入的音频文件</p><p><el-icon><CircleCheck /></el-icon>{{ form.autoProcess ? '文件稳定后自动创建任务' : '保留文件事件，等待手动处理' }}</p><p><el-icon><CircleCheck /></el-icon>保持原有目录结构</p></section>
      </aside>
    </div>
    <template #footer><div class="dialog-footer"><span>{{ mode === 'edit' && folder?.watching ? '正在监听的目录会立即应用新规则' : '保存后可在监控目录列表中启用或停用' }}</span><div><el-button @click="emit('update:modelValue', false)">取消</el-button><el-button type="primary" :disabled="!isValid" @click="emit('submit')">{{ mode === 'create' ? '添加监控目录' : '保存更改' }}</el-button></div></div></template>
  </el-dialog>
</template>

<style scoped>
:global(.watch-editor-dialog) { margin-top: 4vh !important; }
:global(.watch-editor-dialog .el-dialog__body) { max-height: calc(92vh - 120px); overflow: auto; }
.watch-editor-layout { display: grid; grid-template-columns: minmax(0, 1fr) 300px; min-height: 630px; margin: -20px; }.watch-editor-main { padding: 24px 28px; }.watch-editor-header { display: flex; align-items: center; gap: 13px; }.folder-symbol { display: grid; width: 48px; height: 48px; place-items: center; color: #0c9c68; background: #e5f4ef; border-radius: 12px; font-size: 22px; }.watch-editor-header > div:nth-child(2) { flex: 1; }.watch-editor-header span { color: #84908b; font-size: 10px; }.watch-editor-header h3 { margin: 4px 0 0; color: #26342e; font-size: 21px; }
.path-flow { display: grid; grid-template-columns: 1fr 35px 1fr; align-items: end; gap: 10px; padding: 17px; margin: 20px 0; background: #f6f8f7; border-radius: 11px; }.path-flow > div { min-width: 0; }.path-flow span { display: block; margin-bottom: 7px; color: #89948f; font-size: 10px; }.path-flow code { display: block; overflow: hidden; color: #394942; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.path-flow > .el-icon { align-self: center; color: #0c9c68; }
.rule-sections { border-top: 0; }.rule-sections :deep(.el-collapse-item__header) { height: 58px; border: 1px solid #e5ebe8; border-radius: 10px; padding: 0 14px; margin-top: 9px; }.rule-sections :deep(.el-collapse-item__wrap) { border: 0; }.rule-sections :deep(.el-collapse-item__content) { padding: 15px 12px 3px; }.rule-title { display: flex; align-items: center; gap: 9px; flex: 1; }.rule-title > span { display: grid; width: 23px; height: 23px; place-items: center; color: #fff; background: #0c9c68; border-radius: 50%; font-size: 10px; }.rule-title strong { color: #087955; font-size: 13px; }.rule-title small { margin-left: auto; color: #98a19d; font-size: 10px; font-weight: 400; }.rule-form { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }.rule-form :deep(.el-form-item) { margin-bottom: 10px; }.rule-form :deep(.el-select) { width: 100%; }.rule-form .el-form-item:only-child { grid-column: 1 / -1; }.option-meta { float: right; color: #9aa39f; }.path-tip { color: #8d9793; font-size: 10px; }
.rule-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 18px; }.switch-setting { display: flex; align-items: flex-start; justify-content: space-between; padding: 12px; background: #f7f9f8; border-radius: 9px; }.switch-setting > div { display: flex; flex-direction: column; gap: 4px; }.switch-setting strong { font-size: 11px; }.switch-setting span, .readonly-setting small { color: #8d9793; font-size: 9px; }.readonly-setting { display: grid; grid-template-columns: 1fr auto; gap: 5px; padding: 9px 12px; background: #f7f9f8; border-radius: 9px; font-size: 10px; }.readonly-setting small { grid-column: 1 / -1; }
.impact-rail { padding: 25px 22px; background: #fbfcfc; border-left: 1px solid #e7ece9; }.rail-eyebrow { color: #0c9c68; font-size: 10px; font-weight: 800; letter-spacing: .1em; }.check-state { display: flex; gap: 9px; padding: 13px; margin: 13px 0 20px; color: #b87818; background: #fff7e8; border-radius: 9px; }.check-state.valid { color: #087955; background: #e8f5f0; }.check-state > div { display: flex; flex-direction: column; gap: 3px; }.check-state strong { color: #36443e; font-size: 11px; }.check-state span { font-size: 9px; }.impact-rail section { padding: 15px 0; border-top: 1px solid #e6ebe8; }.impact-rail h4 { margin: 0 0 11px; color: #53605b; font-size: 11px; }.impact-rail dl { margin: 0; }.impact-rail dl div { display: flex; justify-content: space-between; min-height: 27px; }.impact-rail dt { color: #8e9894; font-size: 10px; }.impact-rail dd { margin: 0; font-size: 10px; font-weight: 600; }.profile-tags { display: flex; flex-wrap: wrap; gap: 6px; }.profile-tags > span:not(.el-tag) { color: #969f9b; font-size: 10px; }.safety-note { display: flex; gap: 9px; color: #b67818; }.safety-note div { display: flex; flex-direction: column; gap: 5px; }.safety-note strong { color: #745018; font-size: 11px; }.safety-note span { font-size: 9px; line-height: 1.6; }.behavior-list p { display: flex; align-items: center; gap: 6px; margin: 8px 0; color: #66736e; font-size: 10px; }.behavior-list .el-icon { color: #0c9c68; }
.dialog-footer { display: flex; align-items: center; justify-content: space-between; }.dialog-footer > span { color: #8d9793; font-size: 11px; }
@media (max-width: 850px) { .watch-editor-layout { grid-template-columns: 1fr; }.impact-rail { display: none; }.rule-title small { display: none; } }
</style>
