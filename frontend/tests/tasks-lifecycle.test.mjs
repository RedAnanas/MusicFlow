import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'

function setupTasks(seed = {}) {
  const source = readFileSync(new URL('../src/views/Tasks.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  let mounted, unmounted, finishInitialization
  const pending = new Promise(resolve => { finishInitialization = resolve })
  const timers = new Map()
  const calls = []
  const store = {
    tasks: seed.tasks || [], logs: [], profiles: seed.profiles || [],
    fetchTasks: silent => { calls.push(['tasks', silent]); return pending },
    fetchLogs: (limit, silent) => { calls.push(['logs', limit, silent]); return pending },
    fetchProfiles: () => pending,
  }
  const axios = { get: () => { calls.push(['acquisitions']); return pending.then(() => ({data: seed.jobs || []})) } }
  const state = new Function('vue', 'store', 'axios', 'onMounted', 'onUnmounted', 'setInterval', 'clearInterval', `
    const { computed, ref, watch } = vue
    const useAppStore = () => store, useRoute = () => ({ query: {} }), useRouter = () => ({})
    ${ts.transpile(script)}
    return { target, status, keyword, page, records, filteredTasks, acquisitions, fetchAcquisitions }
  `)(vue, store, axios, callback => { mounted = callback }, callback => { unmounted = callback },
    (callback, delay) => { const id = Symbol(); timers.set(id, { callback, delay }); return id },
    id => timers.delete(id))
  return { ...state, mounted, unmounted, finishInitialization, timers, calls, axios }
}

test('任务页初始化完成前离页不会遗留后台轮询', async () => {
  const state = setupTasks()
  const initialization = state.mounted()
  state.unmounted()
  state.finishInitialization()
  await initialization
  assert.equal(state.timers.size, 0)
})

test('任务页正常初始化后静默轮询且离页清理全部计时器', async () => {
  const state = setupTasks()
  const initialization = state.mounted()
  state.finishInitialization()
  await initialization
  assert.equal(state.timers.size, 2)
  const poll = [...state.timers.values()].find(timer => timer.delay === 5000)
  poll.callback()
  assert.deepEqual(state.calls.at(-2), ['tasks', true])
  assert.deepEqual(state.calls.at(-1), ['acquisitions'])
  state.unmounted()
  assert.equal(state.timers.size, 0)
})


test('操作记录合并本地复制与转换，同次双库任务去重并按目标显示状态', async () => {
  const state = setupTasks({
    profiles:[{id:'local',name:'已修改方案',appleMusicDeliveryMode:'direct_upload'}],
    tasks: [
      {id:'routed',source_file:'/in/song.flac',profile_id:'apple',status:'success'},
      {id:'local',source_file:'/in/song.flac',profile_id:'local',status:'success',apple_music_delivery_mode:'none'},
      {id:'apple',source_file:'/in/apple.flac',profile_id:'deleted',apple_music_delivery_mode:'direct_upload',status:'success'},
    ],
    jobs: [
      {id:'both',desired_nas:true,desired_apple:true,nas_status:'success',apple_status:'failed',status:'partial',conversion_task_ids:['routed'],selected_track:{song_name:'双库曲目',singers:'歌手'},created_at:'2026-10-23'},
      {id:'copy',desired_nas:true,desired_apple:false,nas_status:'success',apple_status:'not_needed',status:'completed',selected_track:{song_name:'复制入库'},created_at:'2026-10-22'},
    ],
  })
  const initialization = state.mounted(); state.finishInitialization(); await initialization
  assert.equal(state.records.value.length, 4)
  assert.ok(!state.records.value.some(record => record.task?.id === 'routed'))
  state.target.value = 'local'
  assert.deepEqual(state.filteredTasks.value.map(record => record.id), ['acquisition:both','acquisition:copy','task:local'])
  assert.equal(state.filteredTasks.value[0].status, 'success')
  state.target.value = 'apple'; state.status.value = 'failed'
  assert.deepEqual(state.filteredTasks.value.map(record => record.id), ['acquisition:both'])
  state.status.value = 'all'; state.keyword.value = '歌手'
  assert.equal(state.filteredTasks.value.length, 1)
  state.page.value = 2; state.target.value = 'all'; await vue.nextTick()
  assert.equal(state.page.value, 1)
  state.unmounted()
})

test('上传关联按任务 ID 去重，补齐记录读取失败时保留已有结果', async () => {
  const state = setupTasks({tasks:[{id:'conversion',source_file:'/old/path',status:'success'}], jobs:[{id:'fill',desired_nas:false,desired_apple:true,apple_status:'cloud_completed',nas_status:'not_needed',status:'completed',apple_upload:{state:'cloud_completed',sources:[{conversion_task_id:'conversion'}]},created_at:'2026-10-23'}]})
  const initialization = state.mounted(); state.finishInitialization(); await initialization
  assert.equal(state.records.value.length, 1)
  state.axios.get = async () => { throw new Error('offline') }
  await state.fetchAcquisitions(true)
  assert.equal(state.records.value.length, 1)
  assert.equal(state.records.value[0].status, 'success')
  state.unmounted()
})
