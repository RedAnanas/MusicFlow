import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'

function setupPlayer() {
  const source = readFileSync(new URL('../src/components/MusicPlayer.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  let cleanup
  const requests = []
  const tracks = ['一', '二', '三'].map(token => ({ token, song_name: token, singers: '歌手', stream_url: `/stream/${token}`, lyrics_url: `/lyrics/${token}` }))
  const context = { state: 'running', destination: {}, createMediaElementSource: () => ({ connect() {} }), createAnalyser: () => ({ frequencyBinCount: 64, connect() {} }), close() { this.closed = true } }
  const state = new Function('vue', 'inputProps', 'axios', 'onBeforeUnmount', 'AudioContext', `
    const { ref, computed, watch, nextTick } = vue
    const defineProps = () => inputProps, defineExpose = () => {}, onMounted = () => {}
    const ElMessage = { error(message) { throw new Error(message) } }
    const window = { removeEventListener() {} }
    ${ts.transpile(script, { target: ts.ScriptTarget.ES2022 })}
    return { audio, currentTrack, playing, currentTime, totalTime, volume, lyrics, playTrack, stepTrack, togglePlayback, seek, handleShortcut }
  `)(vue, { tracks }, { get: url => new Promise(resolve => requests.push({ url, resolve })) }, fn => { cleanup = fn }, function () { return context })
  state.audio.value = { src: '', paused: true, currentTime: 0, volume: 1, async play() { this.paused = false }, pause() { this.paused = true }, removeAttribute() { this.src = '' }, load() {} }
  return { ...state, tracks, requests, cleanup: () => cleanup(), context }
}

test('共享播放器播放、切歌、音量和进度控制共用同一音频实例', async () => {
  const state = setupPlayer()
  await state.playTrack(state.tracks[0])
  assert.equal(state.audio.value.src, '/stream/一')
  assert.equal(state.audio.value.volume, 0.75)
  await state.togglePlayback()
  assert.equal(state.audio.value.paused, true)
  state.totalTime.value = 120
  state.currentTime.value = 42
  state.seek()
  assert.equal(state.audio.value.currentTime, 42)
  state.stepTrack(1)
  await vue.nextTick()
  assert.equal(state.currentTrack.value.token, '二')
  assert.equal(state.currentTime.value, 0)
  state.stepTrack(-1)
  state.stepTrack(-1)
  assert.equal(state.currentTrack.value.token, '一')
  state.tracks.splice(0, 1)
  state.stepTrack(1)
  assert.equal(state.currentTrack.value.token, '一')
  state.cleanup()
  assert.equal(state.audio.value.paused, true)
  assert.equal(state.audio.value.src, '')
  assert.equal(state.context.closed, true)
})

test('快速切歌后旧歌词不能覆盖当前曲目，输入时空格不触发播放', async () => {
  const state = setupPlayer()
  await state.playTrack(state.tracks[0])
  await state.playTrack(state.tracks[1])
  state.requests[1].resolve({ data: { lyric: '[00:02]当前歌词' } })
  await vue.nextTick()
  state.requests[0].resolve({ data: { lyric: '[00:01]旧歌词' } })
  await vue.nextTick()
  assert.equal(state.lyrics.value[0].text, '当前歌词')
  state.handleShortcut({ target: { tagName: 'INPUT' }, code: 'Space', preventDefault() { assert.fail('输入框不能拦截空格') } })
  assert.equal(state.audio.value.paused, false)
  state.cleanup()
})
