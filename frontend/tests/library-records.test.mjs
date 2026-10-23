import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'

function setupRecords(axios = {}, ElMessage = {}, ElMessageBox = {}) {
  const source = readFileSync(new URL('../src/views/LibraryReconciliation.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  // 直接执行组件脚本的真实响应式逻辑，不挂载页面或发起网络请求。
  return new Function('vue', 'axios', 'ElMessage', 'ElMessageBox', `
    const { ref, reactive, computed, watch } = vue
    const onMounted = () => {}, useRouter = () => ({}), useAppStore = () => ({})
    ${ts.transpile(script)}
    return { incrementalEntries, incrementalSearch, incrementalFilter, incrementalPage,
      incrementalPageSize, filteredIncrementalEntries, pagedIncrementalEntries, summary,
      reconciliationTotal, statusOptions, reviewData, duplicateRecords, snapshot,
      statusFilter, entries, total, loading, localOnlyCandidates, loadReconciliation,
      mediaSources, selectedCandidates, selectedReviews, removeMediaSource, deleteSnapshot,
      reviewEntryId, reviewSearch, reviewOpen, reviewLoading, loadIncrementalReview,
      openIncrementalReview, batchSave, batchSaving }
  `)(vue, axios, ElMessage, ElMessageBox)
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

function setupReconciliation() {
  const requests = []
  const errors = []
  const axios = { isAxiosError: error => !!error?.response }
  for (const method of ['get', 'post', 'delete']) {
    axios[method] = (url, config = {}) => new Promise((resolve, reject) => requests.push({ method, url, ...config.params, resolve, reject }))
  }
  const state = setupRecords(axios, { error: message => errors.push(message), success() {} }, { confirm: () => Promise.resolve() })
  state.snapshot.value = { id: 'snapshot' }
  return { ...state, requests, errors }
}

const reconciliationResponse = (id, status = 'nas_only', revision = 'revision-1') => ({ data: {
  revision,
  entries: [{ id, status, local: status === 'nas_only' ? { id } : null, candidates: [] }],
  summary: { both: 0, nas_only: status === 'nas_only' ? 1 : 0, apple_only: status === 'apple_only' ? 1 : 0, review: 0 },
  total: 1,
} })

test('快速筛选后较晚返回的旧对账结果不能覆盖新结果', async () => {
  const state = setupReconciliation()
  const oldRequest = state.loadReconciliation()
  state.statusFilter.value = 'nas_only'
  const latestRequest = state.loadReconciliation()
  state.requests[1].resolve(reconciliationResponse('latest'))
  await latestRequest
  state.requests[0].resolve(reconciliationResponse('old'))
  await oldRequest
  assert.equal(state.entries.value[0].id, 'latest')
  assert.equal(state.total.value, 1)
  assert.equal(state.loading.value, false)
})

test('旧对账请求完成或失败不能提前关闭最新加载状态或弹出错误', async () => {
  for (const rejected of [false, true]) {
    const state = setupReconciliation()
    const oldRequest = state.loadReconciliation()
    const latestRequest = state.loadReconciliation()
    if (rejected) state.requests[0].reject(new Error('旧请求失败'))
    else state.requests[0].resolve(reconciliationResponse('old'))
    await oldRequest
    assert.equal(state.loading.value, true)
    assert.deepEqual(state.entries.value, [])
    assert.deepEqual(state.errors, [])
    state.requests[1].reject(new Error('最新请求失败'))
    await latestRequest
    assert.equal(state.loading.value, false)
    assert.deepEqual(state.errors, ['对账失败'])
  }
})

test('旧对账请求加载中的本地候选不能覆盖最新候选', async () => {
  const state = setupReconciliation()
  const oldRequest = state.loadReconciliation()
  state.requests[0].resolve(reconciliationResponse('old', 'apple_only'))
  await Promise.resolve()
  const latestRequest = state.loadReconciliation()
  state.requests[2].resolve(reconciliationResponse('latest', 'apple_only'))
  await Promise.resolve()
  state.requests[3].resolve(reconciliationResponse('latest-candidate'))
  await latestRequest
  state.requests[1].resolve(reconciliationResponse('old-candidate'))
  await oldRequest
  assert.equal(state.entries.value[0].id, 'latest')
  assert.equal(state.localOnlyCandidates.value[0].id, 'latest-candidate')
})

test('同一对账版本翻页复用候选，版本改变和重新扫描后重新读取', async () => {
  const state = setupReconciliation()
  let request = state.loadReconciliation()
  state.requests[0].resolve(reconciliationResponse('first', 'apple_only'))
  await Promise.resolve()
  state.requests[1].resolve(reconciliationResponse('candidate'))
  await request
  request = state.loadReconciliation()
  state.requests[2].resolve(reconciliationResponse('second', 'apple_only'))
  await Promise.resolve()
  assert.equal(state.requests.length, 3)
  await request
  assert.equal(state.localOnlyCandidates.value[0].id, 'candidate')
  request = state.loadReconciliation(true)
  state.requests[3].resolve(reconciliationResponse('third', 'apple_only', 'revision-2'))
  await Promise.resolve()
  assert.equal(state.requests[4].expected_revision, 'revision-2')
  state.requests[4].resolve(reconciliationResponse('new-candidate', 'nas_only', 'revision-2'))
  await request
  assert.equal(state.localOnlyCandidates.value[0].id, 'new-candidate')
})

test('空候选也可复用，读取失败不缓存以便下一次重试', async () => {
  const state = setupReconciliation()
  let request = state.loadReconciliation()
  state.requests[0].resolve(reconciliationResponse('first', 'apple_only'))
  await Promise.resolve()
  state.requests[1].reject(new Error('读取失败'))
  await request
  request = state.loadReconciliation()
  state.requests[2].resolve(reconciliationResponse('second', 'apple_only'))
  await Promise.resolve()
  state.requests[3].resolve({ data: { revision: 'revision-1', entries: [], total: 0 } })
  await request
  request = state.loadReconciliation()
  state.requests[4].resolve(reconciliationResponse('third', 'apple_only'))
  await Promise.resolve()
  assert.equal(state.requests.length, 5)
  await request
  assert.deepEqual(state.localOnlyCandidates.value, [])
})

test('移除最后一个目录后，旧对账响应不能回填列表、候选或选择', async () => {
  const state = setupReconciliation()
  state.mediaSources.value = [{ id: 'source', name: '音乐库' }]
  state.localOnlyCandidates.value = [{ id: 'old-candidate' }]
  state.selectedCandidates.old = 'old-candidate'
  state.selectedReviews.value = [{ id: 'old', status: 'review' }]
  const oldRequest = state.loadReconciliation()
  const removal = state.removeMediaSource(state.mediaSources.value[0])
  await Promise.resolve()
  state.requests[1].resolve({ data: {} })
  await Promise.resolve()
  state.requests[2].resolve({ data: [] })
  await removal
  state.requests[0].resolve(reconciliationResponse('old'))
  await oldRequest
  assert.deepEqual(state.entries.value, [])
  assert.equal(state.total.value, 0)
  assert.equal(state.reconciliationTotal.value, 0)
  assert.equal(state.loading.value, false)
  assert.deepEqual(state.localOnlyCandidates.value, [])
  assert.deepEqual(state.selectedReviews.value, [])
  assert.deepEqual(state.selectedCandidates, {})
})

test('删除快照后，候选在途请求的成功、失败及收尾均不能恢复旧上下文', async () => {
  for (const rejected of [false, true]) {
    const state = setupReconciliation()
    const oldRequest = state.loadReconciliation()
    state.requests[0].resolve(reconciliationResponse('old', 'apple_only'))
    await Promise.resolve()
    const deletion = state.deleteSnapshot()
    await Promise.resolve()
    state.requests[2].resolve({ data: {} })
    await Promise.resolve()
    state.requests[3].resolve({ data: { snapshot: null } })
    await Promise.resolve()
    await Promise.resolve()
    state.requests[4].resolve({ data: [] })
    await deletion
    if (rejected) state.requests[1].reject(new Error('旧候选读取失败'))
    else state.requests[1].resolve(reconciliationResponse('old-candidate'))
    await oldRequest
    assert.equal(state.snapshot.value, null)
    assert.deepEqual(state.entries.value, [])
    assert.deepEqual(state.localOnlyCandidates.value, [])
    assert.equal(state.loading.value, false)
    assert.deepEqual(state.errors, [])
  }
})

test('同一记录重开或连续搜索后，旧详情成功、失败及收尾不能影响新请求', async () => {
  for (const reopen of [false, true]) {
    for (const rejected of [false, true]) {
      const state = setupReconciliation()
      state.reviewEntryId.value = 'entry'
      state.reviewOpen.value = true
      state.reviewSearch.value = '旧搜索词'
      const oldRequest = state.loadIncrementalReview()
      if (reopen) {
        state.reviewOpen.value = false
        await vue.nextTick()
        assert.equal(state.reviewLoading.value, false)
        state.openIncrementalReview({ id: 'entry' })
      } else {
        state.reviewSearch.value = '新搜索词'
        void state.loadIncrementalReview()
      }
      if (rejected) state.requests[0].reject(new Error('旧详情读取失败'))
      else state.requests[0].resolve({ data: { entry: { id: 'entry' }, candidates: [{ title: '旧搜索结果' }] } })
      await oldRequest
      assert.equal(state.reviewLoading.value, true)
      assert.equal(state.reviewData.value, null)
      assert.deepEqual(state.errors, [])
      state.requests[1].resolve({ data: { entry: { id: 'entry' }, candidates: [{ title: '新候选' }] } })
      await Promise.resolve()
      assert.equal(state.reviewData.value.candidates[0].title, '新候选')
      assert.equal(state.reviewLoading.value, false)
    }
  }
})

test('批量保存期间忽略重复或相反操作，失败提示原因并保留选择以便重试', async () => {
  for (const rejected of [false, true]) {
    const state = setupReconciliation()
    state.snapshot.value = null
    state.selectedReviews.value = [{ id: 'review', status: 'review', apple: { track_key: 'apple' } }]
    state.selectedCandidates.review = 'local'
    const request = state.batchSave('confirmed')
    const duplicate = state.batchSave('rejected')
    assert.equal(state.batchSaving.value, true)
    const submitted = state.requests.length
    if (rejected) state.requests[0].reject({ response: { data: { detail: '候选已失效' } } })
    else state.requests[0].resolve({ data: {} })
    // 即便旧实现重复提交，仍完成请求，确保断言只检查防重结果。
    for (const pending of state.requests.slice(1)) pending.resolve({ data: {} })
    await Promise.all([request, duplicate])
    assert.equal(state.batchSaving.value, false)
    assert.equal(submitted, 1)
    assert.deepEqual(state.errors, rejected ? ['候选已失效'] : [])
    if (rejected) {
      assert.equal(state.selectedReviews.value[0].id, 'review')
      assert.equal(state.selectedCandidates.review, 'local')
      const retry = state.batchSave('confirmed')
      assert.equal(state.requests.length, 2)
      state.requests[1].resolve({ data: {} })
      await retry
    }
  }
})
