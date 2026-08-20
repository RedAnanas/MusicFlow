<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Profile } from '../types'

export interface ProfileEditorForm {
  name: string
  outputFormat: Profile['outputFormat']
  codec: string
  bitrate: number
  sampleRate: number
  metadataPolicy: Profile['metadataPolicy']
  coverPolicy: Profile['coverPolicy']
  filenameTemplate: string
  directoryTemplate: string
  appleMusicHandoffEnabled: boolean
  appleMusicImportDir: string
}

const props = defineProps<{ modelValue: boolean; mode: 'create' | 'edit'; form: ProfileEditorForm }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; submit: [] }>()
const activeSection = ref('basic')

watch(() => props.modelValue, visible => { if (visible) activeSection.value = 'basic' })

const sections = [
  { key: 'basic', label: '基本信息' },
  { key: 'quality', label: '音频质量' },
  { key: 'metadata', label: '元数据封面' },
  { key: 'naming', label: '命名输出' },
  { key: 'handoff', label: '自动交接' },
]
const lossless = computed(() => ['alac', 'flac', 'pcm_s16le'].includes(props.form.codec))
const isValid = computed(() => props.form.name.trim() && props.form.filenameTemplate.trim() && props.form.directoryTemplate.trim())
</script>

<template>
  <el-dialog :model-value="modelValue" :title="mode === 'create' ? '新建转换方案' : '编辑转换方案'" width="880px" class="workspace-dialog profile-editor-dialog" destroy-on-close @update:model-value="emit('update:modelValue', $event)">
    <div class="editor-layout">
      <nav class="editor-steps" aria-label="方案设置步骤">
        <button v-for="section in sections" :key="section.key" type="button" :class="{ active: activeSection === section.key }" @click="activeSection = section.key">{{ section.label }}</button>
      </nav>

      <el-form :model="form" label-position="top" class="editor-form">
        <section v-show="activeSection === 'basic'">
          <div class="section-heading"><div><span>01</span><h3>基本信息</h3></div><p>为方案设置清晰的名称和目标格式。</p></div>
          <el-form-item label="方案名称" required><el-input v-model="form.name" maxlength="40" show-word-limit placeholder="例如：Apple Music AAC 256" /></el-form-item>
          <div class="two-column"><el-form-item label="输出格式"><el-select v-model="form.outputFormat"><el-option v-for="format in ['m4a','mp3','flac','alac','wav','ogg','opus']" :key="format" :label="format.toUpperCase()" :value="format" /></el-select></el-form-item><el-form-item label="编码器"><el-select v-model="form.codec" filterable><el-option label="AAC（推荐）" value="aac" /><el-option label="ALAC（无损）" value="alac" /><el-option label="MP3" value="libmp3lame" /><el-option label="FLAC（无损）" value="flac" /><el-option label="Vorbis" value="libvorbis" /><el-option label="Opus" value="libopus" /><el-option label="PCM" value="pcm_s16le" /></el-select></el-form-item></div>
          <div class="form-callout"><el-icon><InfoFilled /></el-icon><span>方案会同时控制编码参数、标签、封面和输出命名。</span></div>
        </section>

        <section v-show="activeSection === 'quality'">
          <div class="section-heading"><div><span>02</span><h3>音频质量</h3></div><p>选择与目标设备和存储空间匹配的质量。</p></div>
          <div class="two-column"><el-form-item label="比特率"><el-select v-model="form.bitrate" :disabled="lossless"><el-option v-for="rate in [64,96,128,160,192,224,256,320]" :key="rate" :label="`${rate} kbps`" :value="rate" /></el-select><small v-if="lossless" class="field-tip">无损编码无需设置比特率</small></el-form-item><el-form-item label="采样率"><el-select v-model="form.sampleRate" clearable placeholder="保持源文件"><el-option label="44100 Hz" :value="44100" /><el-option label="48000 Hz" :value="48000" /><el-option label="96000 Hz" :value="96000" /></el-select></el-form-item></div>
          <div class="quality-summary"><span>编码结果</span><strong>{{ form.outputFormat.toUpperCase() }} · {{ form.codec.toUpperCase() }} · {{ lossless ? '无损' : `${form.bitrate} kbps` }}</strong></div>
        </section>

        <section v-show="activeSection === 'metadata'">
          <div class="section-heading"><div><span>03</span><h3>元数据与封面</h3></div><p>决定标题、艺术家、歌词和专辑封面的处理方式。</p></div>
          <div class="two-column"><el-form-item label="元数据策略"><el-select v-model="form.metadataPolicy"><el-option label="保留源文件元数据" value="keep" /><el-option label="覆盖元数据" value="overwrite" /><el-option label="不写入元数据" value="strip" /></el-select></el-form-item><el-form-item label="封面策略"><el-select v-model="form.coverPolicy"><el-option label="保留" value="keep" /><el-option label="嵌入" value="embed" /><el-option label="保留并嵌入" value="keep_and_embed" /><el-option label="不处理" value="strip" /></el-select></el-form-item></div>
          <div class="form-callout"><el-icon><Picture /></el-icon><span>{{ form.metadataPolicy === 'strip' ? '输出文件将不包含歌曲标签。' : '标题、艺术家、专辑和歌词将按所选策略处理。' }}</span></div>
        </section>

        <section v-show="activeSection === 'naming'">
          <div class="section-heading"><div><span>04</span><h3>命名与输出</h3></div><p>使用变量构建稳定、可预测的目录结构。</p></div>
          <el-form-item label="文件名模板" required><el-input v-model="form.filenameTemplate" /><div class="token-row"><el-tag size="small" effect="plain">{'{title}'}</el-tag><el-tag size="small" effect="plain">{'{extension}'}</el-tag></div></el-form-item>
          <el-form-item label="目录模板" required><el-input v-model="form.directoryTemplate" /><div class="token-row"><el-tag size="small" effect="plain">{'{album_artist}'}</el-tag><el-tag size="small" effect="plain">{'{year}'}</el-tag><el-tag size="small" effect="plain">{'{album}'}</el-tag></div></el-form-item>
        </section>

        <section v-show="activeSection === 'handoff'">
          <div class="section-heading"><div><span>05</span><h3>Apple Music 自动交接</h3></div><p>转换完成后复制到 Apple Music 自动导入目录。</p></div>
          <div class="switch-row"><div><strong>启用自动交接</strong><span>仅表示文件已交给 Apple Music，不代表云端上传成功。</span></div><el-switch v-model="form.appleMusicHandoffEnabled" /></div>
          <el-form-item v-if="form.appleMusicHandoffEnabled" label="自动导入目录"><el-input v-model="form.appleMusicImportDir" placeholder="/mnt/d/.../Automatically Add to Apple Music" /></el-form-item>
        </section>
      </el-form>

    </div>
    <template #footer><div class="dialog-footer"><span>{{ mode === 'edit' ? '修改将用于之后创建的转换任务' : '保存后可立即在转换任务中使用' }}</span><div><el-button @click="emit('update:modelValue', false)">取消</el-button><el-button type="primary" :disabled="!isValid" @click="emit('submit')">{{ mode === 'create' ? '创建方案' : '保存更改' }}</el-button></div></div></template>
  </el-dialog>
</template>

<style scoped>
:global(.profile-editor-dialog .el-dialog__body) { width: auto; padding: 0; }
.editor-layout { min-height: 500px; }
.editor-steps { display: grid; grid-template-columns: repeat(5, 1fr); padding: 0 24px; background: #f7f9f8; border-bottom: 1px solid #e7ece9; }
.editor-steps button { position: relative; padding: 17px 8px; color: #6e7a75; background: transparent; border: 0; cursor: pointer; }
.editor-steps button::after { position: absolute; right: 18px; bottom: -1px; left: 18px; height: 2px; content: ''; background: transparent; }
.editor-steps button.active { color: #087955; font-weight: 700; }.editor-steps button.active::after { background: #0c9c68; }
.editor-form { max-width: 760px; padding: 28px 34px; margin: 0 auto; }.editor-form section { width: 100%; }.section-heading { padding-bottom: 17px; margin-bottom: 22px; border-bottom: 1px solid #e9eeeb; }.section-heading > div { display: flex; align-items: center; gap: 9px; }.section-heading span { color: #0c9c68; font-size: 11px; font-weight: 800; }.section-heading h3 { margin: 0; font-size: 18px; }.section-heading p { margin: 7px 0 0; color: #8b9691; font-size: 12px; }
.two-column { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }.editor-form :deep(.el-select) { width: 100%; }.field-tip { color: #a37b2d; font-size: 10px; }.form-callout, .quality-summary { display: flex; align-items: center; gap: 9px; padding: 13px; color: #61716a; background: #f2f6f4; border-radius: 9px; font-size: 11px; }.form-callout .el-icon { color: #0c9c68; }.quality-summary { justify-content: space-between; }.quality-summary strong { color: #26342e; }
.token-row { display: flex; gap: 6px; margin-top: 8px; }.switch-row { display: flex; align-items: flex-start; justify-content: space-between; padding: 15px; margin-bottom: 20px; background: #f7f9f8; border-radius: 10px; }.switch-row > div { display: flex; flex-direction: column; gap: 5px; }.switch-row strong { font-size: 13px; }.switch-row span { color: #87928d; font-size: 11px; }
.dialog-footer { display: flex; align-items: center; justify-content: space-between; }.dialog-footer > span { color: #8d9793; font-size: 11px; }
@media (max-width: 700px) { .editor-steps { grid-template-columns: repeat(3, 1fr); }.editor-form { padding: 24px; }.two-column { grid-template-columns: 1fr; } }
</style>
