import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'

function setupProgress(upload = { id: 'upload-1', updated_at: 1, current_timing: { stage: 'audio', progress: 25 } }) {
  const source = readFileSync(new URL('../src/components/UploadProgress.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const requests = []
  const props = vue.reactive({ upload, now: 1000 })
  const state = new Function('vue', 'inputProps', 'axios', `
    const { computed, ref, watch } = vue
    const defineProps = () => inputProps
    ${ts.transpile(script)}
    return { current, timelineUpload, detailsLoading, detailsError, toggleDetails }
  `)(vue, props, { get: url => new Promise((resolve, reject) => requests.push({ url, resolve, reject })) })
  return { ...state, props, requests }
}

test('上传摘要保留实时进度，仅展开时读取明细，收起后不自动读取', async () => {
  const state = setupProgress()
  assert.equal(state.current.value.progress, 25)
  assert.equal(state.requests.length, 0)
  const opening = state.toggleDetails({ target: { open: true } })
  assert.equal(state.requests[0].url, '/api/apple-music/uploads/upload-1')
  state.requests[0].resolve({ data: { id: 'upload-1', timeline: [{ stage: 'audio' }] } })
  await opening
  assert.equal(state.timelineUpload.value.timeline.length, 1)
  await state.toggleDetails({ target: { open: false } })
  state.props.upload.updated_at = 2
  await vue.nextTick()
  assert.equal(state.requests.length, 1)
})

test('展开中的上传明细随状态更新且旧响应不能覆盖新响应', async () => {
  const state = setupProgress()
  const opening = state.toggleDetails({ target: { open: true } })
  state.props.upload.updated_at = 2
  await vue.nextTick()
  assert.equal(state.requests.length, 2)
  state.requests[1].resolve({ data: { id: 'upload-1', timeline: [{ stage: 'completed' }] } })
  await Promise.resolve()
  state.requests[0].reject(new Error('过期请求失败'))
  await opening
  assert.equal(state.timelineUpload.value.timeline[0].stage, 'completed')
  assert.equal(state.detailsLoading.value, false)
  assert.equal(state.detailsError.value, '')
})

test('已有完整时间线的入口直接复用，摘要明细失败后可重新展开重试', async () => {
  const full = setupProgress({ id: 'full', updated_at: 1, timeline: [] })
  await full.toggleDetails({ target: { open: true } })
  assert.equal(full.requests.length, 0)
  const summary = setupProgress()
  let opening = summary.toggleDetails({ target: { open: true } })
  summary.requests[0].reject(new Error('暂时失败'))
  await opening
  assert.ok(summary.detailsError.value)
  await summary.toggleDetails({ target: { open: false } })
  opening = summary.toggleDetails({ target: { open: true } })
  summary.requests[1].resolve({ data: { id: 'upload-1', timeline: [] } })
  await opening
  assert.equal(summary.detailsError.value, '')
  assert.deepEqual(summary.timelineUpload.value.timeline, [])
})
