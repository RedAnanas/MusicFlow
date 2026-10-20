import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'

function setupRecords() {
  const source = readFileSync(new URL('../src/views/LibraryReconciliation.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  // 直接执行组件脚本的真实响应式逻辑，不挂载页面或发起网络请求。
  return new Function('vue', `
    const { ref, reactive, computed, watch } = vue
    const onMounted = () => {}, useRouter = () => ({}), useAppStore = () => ({})
    ${ts.transpile(script)}
    return { incrementalEntries, incrementalSearch, incrementalFilter, incrementalPage,
      incrementalPageSize, filteredIncrementalEntries, pagedIncrementalEntries, summary,
      reconciliationTotal, statusOptions, reviewData, duplicateRecords }
  `)(vue)
}

test('添加记录按二十条分页，搜索和状态筛选重置页码，删除末页记录自动回退', async () => {
  const state = setupRecords()
  state.incrementalEntries.value = Array.from({ length: 41 }, (_, id) => ({
    id: String(id), title: `歌曲${id}`, artist: '歌手', album: '专辑',
    verification_status: 'manual_confirmed', manual_confirmed_at: '2026-10-20',
    snapshot_status: id === 40 ? 'unmatched' : 'matched',
  }))
  assert.equal(state.pagedIncrementalEntries.value.length, 20)
  state.incrementalPage.value = 3
  assert.equal(state.pagedIncrementalEntries.value[0].id, '40')
  state.incrementalEntries.value.pop()
  await vue.nextTick()
  assert.equal(state.incrementalPage.value, 2)
  state.incrementalSearch.value = '歌曲0'
  await vue.nextTick()
  assert.equal(state.incrementalPage.value, 1)
  assert.equal(state.filteredIncrementalEntries.value.length, 1)
  state.incrementalSearch.value = ''
  state.incrementalFilter.value = 'manual_confirmed'
  await vue.nextTick()
  assert.equal(state.filteredIncrementalEntries.value.length, 40)
  state.incrementalFilter.value = 'pending'
  await vue.nextTick()
  assert.equal(state.filteredIncrementalEntries.value.length, 0)
})

test('全部快捷选择在首位，总数不受当前筛选结果影响', () => {
  const state = setupRecords()
  assert.deepEqual(state.statusOptions[0], { value: '', label: '全部' })
  state.summary.value = { both: 12, nas_only: 3, apple_only: 7, review: 2 }
  assert.equal(state.reconciliationTotal.value, 24)
})

test('名称差异只作为合并候选，不自动合并不同歌手或专辑的版本', () => {
  const state = setupRecords()
  const entry = { id: '1', title: '预谋 (DJ版)', artist: 'DJ', album: '专辑' }
  state.reviewData.value = { entry }
  state.incrementalEntries.value = [entry,
    { id: '2', title: '预谋', artist: 'DJ', album: '专辑' },
    { id: '3', title: '预谋', artist: '其他歌手', album: '专辑' },
    { id: '4', title: '预谋', artist: 'DJ', album: '另一专辑' },
  ]
  assert.deepEqual(state.duplicateRecords.value.map(item => item.id), ['2'])
  assert.equal(state.incrementalEntries.value.length, 4)
})
