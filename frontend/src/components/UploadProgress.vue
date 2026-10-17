<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AppleMusicUpload } from '../types'
import { uploadStageLabel } from '../utils/appleMusicUpload'

const props = defineProps<{ upload: AppleMusicUpload; now: number; conversionStart?: string; conversionEnd?: string; preparationStart?: string }>()
const receivedAt = ref(Date.now())
watch(() => props.upload, () => { receivedAt.value = Date.now() })
const serverNow = computed(() => (props.upload.server_time ?? props.now / 1000) + (props.now - receivedAt.value) / 1000)
const duration = (seconds: number) => {
  const value = Math.max(0, Math.floor(seconds))
  return `${Math.floor(value / 3600) ? `${Math.floor(value / 3600)}时` : ''}${Math.floor(value / 60) % 60}分${value % 60}秒`
}
const stamp = (seconds?: number | null) => seconds == null ? '进行中' : new Date(seconds * 1000).toLocaleString('zh-CN', { hour12: false })
const elapsed = (start: number, end?: number | null) => duration((end ?? serverNow.value) - start)
const current = computed(() => props.upload.timeline?.find(item => item.ended_at == null))
const totalEnd = computed(() => props.upload.finished_at ?? serverNow.value)
const conversionSeconds = computed(() => props.conversionStart && props.conversionEnd ? (Date.parse(props.conversionEnd) - Date.parse(props.conversionStart)) / 1000 : null)
const reused = computed(() => {
  const start = props.preparationStart || props.conversionStart
  return !!start && Date.parse(start) / 1000 > props.upload.created_at
})
</script>

<template>
  <div class="upload-progress">
    <div v-if="upload.created_at">上传流程累计 {{ elapsed(upload.created_at, upload.finished_at) }}（含排队及等待）</div>
    <div v-if="current">
      {{ uploadStageLabel(current.stage) }} · 已耗时 {{ elapsed(current.started_at) }}
      <span v-if="current.progress != null"> · {{ current.progress.toFixed(1) }}%</span>
      <span v-if="current.wait_until != null"> · 距下次查询 {{ Math.max(0, Math.ceil(current.wait_until - serverNow)) }} 秒</span>
      <el-progress v-if="current.progress != null" :percentage="Math.floor(current.progress)" :show-text="false" />
      <small v-if="current.stage === 'audio'">字节传输进度；传输后仍需等待 Apple 确认。</small>
      <small v-if="current.stage !== 'queued' && serverNow - upload.updated_at > 45">执行器近期未上报，当前进度可能已停滞。</small>
    </div>
    <details>
      <summary>查看每个阶段的时间与耗时</summary>
      <p v-if="reused">此歌曲复用了已有上传记录，以下上传时间线属于原任务。</p>
      <p v-if="preparationStart && !reused">补齐任务创建：{{ new Date(preparationStart).toLocaleString('zh-CN', { hour12: false }) }}<br>
        上传前准备（含下载及转换）：{{ duration(upload.created_at - Date.parse(preparationStart) / 1000) }}<br>
        补齐任务创建至{{ upload.finished_at ? '上传结束' : '现在' }}：{{ duration(totalEnd - Date.parse(preparationStart) / 1000) }}</p>
      <p v-if="conversionStart">本地处理开始：{{ new Date(conversionStart).toLocaleString('zh-CN', { hour12: false }) }}<br>
        转换耗时：{{ conversionSeconds == null ? '未记录' : duration(conversionSeconds) }}<br>
        <span v-if="!reused">从本地处理开始至{{ upload.finished_at ? '上传结束' : '现在' }}：{{ duration(totalEnd - Date.parse(conversionStart) / 1000) }}</span></p>
      <p>上传创建：{{ stamp(upload.created_at) }}<br>上传结束：{{ stamp(upload.finished_at) }}</p>
      <p v-if="!upload.timeline?.length">此任务未记录分阶段时间，无法还原历史明细。</p>
      <p v-else-if="upload.timeline[0]!.started_at > upload.created_at">此任务部分阶段未记录，仅显示已有明细。</p>
      <ol v-if="upload.timeline?.length">
        <li v-for="(item, index) in upload.timeline" :key="index">
          <strong>{{ uploadStageLabel(item.stage) || '处理阶段' }}</strong> · {{ elapsed(item.started_at, item.ended_at) }}
          <small>{{ stamp(item.started_at) }} → {{ stamp(item.ended_at) }}</small>
          <small v-if="item.progress != null">最近进度 {{ item.progress.toFixed(1) }}%</small>
        </li>
      </ol>
    </details>
  </div>
</template>

<style scoped>
.upload-progress { margin-top: 8px; font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
summary { cursor: pointer; }
small { display: block; opacity: .75; }
ol { padding-left: 22px; }
li { margin: 8px 0; }
.el-progress { max-width: 360px; margin: 5px 0; }
</style>
