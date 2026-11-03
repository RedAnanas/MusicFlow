import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { ref } from 'vue'
import ts from 'typescript'

const source = readFileSync(new URL('../src/views/Discovery.vue', import.meta.url), 'utf8')
const functions = source.match(/^function (?:finishSearch|searchMusic)\(.*$/gm).join('\n')

test('搜索立即展示所选源的进度，并在完成前逐条显示结果', () => {
  const listeners = {}
  const state = new Function('ref', 'EventSource', `
    const query=ref('歌曲'), selectedSources=ref(['QQMusicClient', 'KuwoMusicClient'])
    const linkTracks=ref([]), results=ref([]), sourceProgress=ref({}), formatFilter=ref(''), sourceFilter=ref(''), searching=ref(false)
    let eventSource=null
    const stopLinkPolling=()=>{}, searchAppleCatalog=()=>{}, ElMessage={error:assertError,warning:assertError}
    function assertError(message) { throw new Error(message) }
    ${ts.transpile(functions, { target: ts.ScriptTarget.ES2022 })}
    return { searchMusic, results, sourceProgress, searching }
  `)(ref, class {
    addEventListener(name, handler) { listeners[name] = handler }
    close() {}
  })
  state.searchMusic()
  assert.equal(state.searching.value, true)
  assert.deepEqual(state.sourceProgress.value, { QQMusicClient: '搜索中', KuwoMusicClient: '搜索中' })
  const emit = (event, data) => listeners[event]({ data: JSON.stringify(data) })
  emit('result', { token: '1', source: 'QQ' })
  assert.equal(state.results.value.length, 1)
  assert.equal(state.searching.value, true)
  emit('source_done', { source: 'QQMusicClient', count: 1 })
  assert.equal(state.sourceProgress.value.QQMusicClient, '完成 · 1 条')
  emit('result', { token: '2', source: 'Kuwo' })
  assert.equal(state.results.value.length, 2)
  emit('done', {})
  assert.equal(state.searching.value, false)
})
