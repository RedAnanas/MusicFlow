<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { DeliveryTarget, Profile, WatchFolder } from '../types'
import { useAppStore } from '../stores/app'
import ServerFileBrowser from './ServerFileBrowser.vue'
import ProfileEditorDialog, { type ProfileEditorForm } from './ProfileEditorDialog.vue'

export interface WatchFolderEditorForm { name: string; inputDir: string; defaultTarget: WatchFolder['defaultTarget']; targets: DeliveryTarget[]; autoProcess: boolean; recursiveScan: boolean; scanIntervalMinutes: number }
const props = defineProps<{ modelValue: boolean; mode: 'create' | 'edit'; form: WatchFolderEditorForm; profiles: Profile[]; folder?: WatchFolder | null; fileStableSeconds: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; submit: [] }>()
const store = useAppStore()
const showDirectoryBrowser = ref(false)
const outputIndex = ref<number | null>(null)
const parameterTarget = ref<DeliveryTarget | null>(null)
const parameterForm = ref<ProfileEditorForm | null>(null)
const parameterOriginal = ref<Profile>()
const showParameters = ref(false)
const isAbsolutePath = (value: string) => value.startsWith('/') || /^[A-Za-z]:[\\/]/.test(value) || value.startsWith('\\\\')
const isValid = computed(() => props.form.name.trim() && (!props.form.inputDir || isAbsolutePath(props.form.inputDir)) && props.form.targets.length > 0 && props.form.targets.every(target => isAbsolutePath(target.outputDir) && (target.type === 'copy' || Boolean(target.profileId))))
const availableProfiles = computed(() => props.profiles.filter(profile => profile.enabled))
const addRule = () => props.form.targets.push({ type: 'convert', profileId: '', outputDir: '' })
const changeType = (target: DeliveryTarget) => { if (target.type === 'copy') { delete target.profileId; delete target.library } }
const selectDirectory = (paths: string[]) => { const path = paths[0] || ''; if (outputIndex.value === null) props.form.inputDir = path; else props.form.targets[outputIndex.value].outputDir = path }
function editParameters(target: DeliveryTarget) {
  parameterTarget.value = target
  const profile = props.profiles.find(item => item.id === target.profileId)
  parameterOriginal.value = profile
  parameterForm.value = {
    name: `${props.form.name || '转换方案'} · 输出 ${props.form.targets.indexOf(target) + 1}`,
    outputFormat: profile?.outputFormat || 'm4a', codec: profile?.codec || 'aac',
    bitrate: profile?.bitrate || 256, sampleRate: profile ? profile.sampleRate : 44100,
    metadataPolicy: profile?.metadataPolicy || 'keep', coverPolicy: profile?.coverPolicy || 'embed',
    filenameTemplate: profile?.filenameTemplate || '{title}.{extension}',
    directoryTemplate: profile?.directoryTemplate || '{album_artist}/{year} - {album}',
    appleMusicHandoffEnabled: profile?.appleMusicHandoffEnabled || false,
    appleMusicDeliveryMode: profile?.appleMusicDeliveryMode || 'none',
    appleMusicImportDir: profile?.appleMusicImportDir || '',
  }
  showParameters.value = true
}
async function saveParameters() {
  if (!parameterForm.value || !parameterTarget.value) return
  try {
    // 为当前规则保存独立参数，避免修改其他方案共用的预设。
    const profile = await store.createProfile({ ...parameterOriginal.value, ...parameterForm.value })
    parameterTarget.value.profileId = profile.id
    showParameters.value = false
    ElMessage.success('转换参数已保存，请继续保存转换方案')
  } catch { ElMessage.error('保存转换参数失败') }
}
</script>

<template>
  <el-dialog :model-value="modelValue" :title="mode === 'create' ? '新建转换方案' : '编辑转换方案'" width="880px" class="workspace-dialog watch-editor-dialog" destroy-on-close @update:model-value="emit('update:modelValue', $event)">
    <div class="editor-layout"><el-form :model="form" label-position="top" class="editor-form">
      <section><div class="section-heading"><div><span>01</span><h3>转换方案</h3></div><p>操作台、资料库补齐和自动监控共同使用这套输出设置。</p></div><el-form-item label="方案名称" required><el-input v-model="form.name" placeholder="例如：双库入库" /></el-form-item></section>
      <section><div class="section-heading"><div><span>02</span><h3>输出规则</h3></div><p>可同时配置原样复制和转换；资料库补齐只使用已启用上传或交接的规则。</p></div>
        <div class="rule-list"><article v-for="(target, index) in form.targets" :key="index" class="rule-card"><header><strong>输出 {{ index + 1 }}</strong><el-button link type="danger" @click="form.targets.splice(index, 1)">删除</el-button></header>
          <div class="rule-fields"><el-form-item label="处理方式"><el-radio-group v-model="target.type" @change="changeType(target)"><el-radio value="convert">转换输出</el-radio><el-radio value="copy">原样复制</el-radio></el-radio-group></el-form-item>
            <el-form-item v-if="target.type === 'convert'" label="转换参数" required><el-select v-model="target.profileId" placeholder="选择已有参数或新建"><el-option v-for="profile in availableProfiles" :key="profile.id" :label="profile.name" :value="profile.id" /></el-select><el-button link type="primary" @click="editParameters(target)">{{ target.profileId ? '调整参数（保存为本方案副本）' : '新建转换参数' }}</el-button></el-form-item>
            <el-form-item label="输出目录" required><el-input v-model="target.outputDir" readonly placeholder="请选择输出目录"><template #append><el-button @click="outputIndex = index; showDirectoryBrowser = true">选择</el-button></template></el-input></el-form-item>
          </div></article><el-button plain class="add-rule" @click="addRule"><el-icon><Plus /></el-icon>添加输出规则</el-button></div>
      </section>
      <section><div class="section-heading"><div><span>03</span><h3>目录监控（可选）</h3></div><p>不设置输入目录时，仅供操作台和对账页手动调用。清除目录不会删除文件。</p></div>
        <el-form-item label="监控输入目录"><el-input v-model="form.inputDir" readonly placeholder="不配置，手动选择歌曲"><template #append><el-button @click="outputIndex = null; showDirectoryBrowser = true">选择</el-button></template></el-input><el-button v-if="form.inputDir" link type="primary" @click="form.inputDir = ''">清除目录，改为手动方案</el-button></el-form-item>
        <div v-if="form.inputDir"><el-form-item label="外部文件默认目标"><el-select v-model="form.defaultTarget"><el-option label="全部输出规则" value="all"/><el-option label="仅本地" value="nas"/><el-option label="仅 Apple Music" value="apple"/><el-option label="双库补齐" value="both"/></el-select></el-form-item>
          <div class="settings-grid"><div class="switch-card"><div><strong>自动处理新文件</strong><small>文件稳定后创建任务</small></div><el-switch v-model="form.autoProcess" /></div><div class="switch-card"><strong>递归扫描子目录</strong><el-switch v-model="form.recursiveScan" /></div><el-form-item label="扫描间隔"><el-select v-model="form.scanIntervalMinutes"><el-option v-for="minutes in [1,5,15,30,60]" :key="minutes" :label="`每 ${minutes} 分钟`" :value="minutes" /></el-select></el-form-item><div class="quality-summary"><span>文件稳定等待</span><strong>{{ fileStableSeconds }} 秒</strong></div></div>
        </div>
      </section>
    </el-form></div>
    <ServerFileBrowser v-model="showDirectoryBrowser" mode="directory" @select="selectDirectory" />
    <ProfileEditorDialog v-if="parameterForm" v-model="showParameters" mode="create" :form="parameterForm" @submit="saveParameters" />
    <template #footer><div class="dialog-footer"><span>{{ isValid ? `保存 ${form.targets.length} 条输出规则` : '请补全方案名称和输出规则' }}</span><div><el-button @click="emit('update:modelValue', false)">取消</el-button><el-button type="primary" :disabled="!isValid" @click="emit('submit')">保存转换方案</el-button></div></div></template>
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
@media(max-width:700px){.editor-form{padding:12px}.editor-form section{padding:14px}.rule-card{padding:10px}.two-column,.rule-fields,.settings-grid{grid-template-columns:1fr}.dialog-footer>span{display:none}}
</style>
