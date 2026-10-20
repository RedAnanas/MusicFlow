<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeftBold, ArrowRightBold, Headset, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import type { PlayerTrack } from '../types'

const props = defineProps<{ tracks: PlayerTrack[] }>()
interface LyricLine { time:number; text:string }
const currentTrack = ref<PlayerTrack | null>(null), audio = ref<HTMLAudioElement | null>(null), visualizer = ref<HTMLCanvasElement | null>(null), lyricsScroll = ref<HTMLElement | null>(null), playing = ref(false)
const currentTime = ref(0), totalTime = ref(0), volume = ref(75), lyricsOpen = ref(false), lyrics = ref<LyricLine[]>([])
const coverFailed = ref(false)
let audioContext: AudioContext | null = null; let analyser: AnalyserNode | null = null; let visualizerData: Uint8Array<ArrayBuffer> | null = null; let visualizerFrame = 0
const activeLyric = computed(() => { let index=-1; for (let i=0;i<lyrics.value.length;i+=1) { if (lyrics.value[i].time<=currentTime.value+.2) index=i; else break } return index })
function drawVisualizer() { const canvas=visualizer.value; if (!canvas) return; const context=canvas.getContext('2d'); if (!context) return; const ratio=window.devicePixelRatio || 1; const width=220*ratio, height=44*ratio; if (canvas.width!==width || canvas.height!==height) { canvas.width=width; canvas.height=height }; context.clearRect(0,0,width,height); if (analyser && visualizerData && !audio.value?.paused) analyser.getByteFrequencyData(visualizerData); const gradient=context.createLinearGradient(0,0,width,0); gradient.addColorStop(0,'#ffb46b'); gradient.addColorStop(1,'#ff6b9d'); context.fillStyle=gradient; const bars=40, gap=2*ratio, barWidth=(width-gap*(bars-1))/bars; for(let i=0;i<bars;i+=1){ const value=analyser && visualizerData && !audio.value?.paused ? visualizerData[Math.floor(i*visualizerData.length/bars)]/255 : .08; const barHeight=Math.max(2*ratio,value*height); const x=i*(barWidth+gap), y=(height-barHeight)/2; context.beginPath(); context.roundRect(x,y,barWidth,barHeight,Math.min(barWidth/2,2*ratio)); context.fill() } visualizerFrame=requestAnimationFrame(drawVisualizer) }
async function ensureAudioGraph() { if (!audio.value) return; if (!audioContext) { audioContext=new AudioContext(); const source=audioContext.createMediaElementSource(audio.value); analyser=audioContext.createAnalyser(); analyser.fftSize=128; analyser.smoothingTimeConstant=.8; source.connect(analyser); analyser.connect(audioContext.destination); visualizerData=new Uint8Array(analyser.frequencyBinCount); await nextTick(); drawVisualizer() } if (audioContext.state==='suspended') await audioContext.resume() }
async function playTrack(track: PlayerTrack) {
  currentTrack.value = track
  coverFailed.value = false
  if (!audio.value) return
  currentTime.value=0; totalTime.value=0; lyrics.value=[]
  audio.value.src = track.stream_url
  setVolume()
  void loadLyrics(false)
  try { await ensureAudioGraph(); await audio.value.play() }
  catch (error) { if (!(error instanceof DOMException && error.name==='AbortError')) ElMessage.error('无法播放该曲目，请检查文件或浏览器格式支持') }
}
async function togglePlayback() { if (!audio.value || !currentTrack.value) return; if (audio.value.paused) { try { await ensureAudioGraph(); await audio.value.play() } catch { ElMessage.error('无法播放该曲目') } } else audio.value.pause() }
function formatTime(value:number) { const seconds=Math.floor(value || 0); return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2,'0')}` }
function seek() { if (audio.value && totalTime.value) audio.value.currentTime=currentTime.value }
function setVolume() { if (audio.value) audio.value.volume=volume.value / 100 }
function stepTrack(direction:number) { if (!currentTrack.value) return; const index=props.tracks.findIndex(track=>track.token===currentTrack.value?.token); const next=index<0 ? undefined : props.tracks[index+direction]; if (next) playTrack(next) }
function parseLyrics(value:string) { const parsed:LyricLine[]=[]; for (const row of (value || '').split('\n')) { const matches=[...row.matchAll(/\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]/g)]; const text=row.replace(/\[[^\]]*\]/g,'').trim(); if (!text) continue; for (const match of matches) parsed.push({time:Number(match[1])*60+Number(match[2])+(match[3]?Number(`0.${match[3]}`):0),text}) } return parsed.sort((a,b)=>a.time-b.time) }
async function loadLyrics(open=true) {
  const track=currentTrack.value
  if (!track?.lyrics_url) return
  if (open) lyricsOpen.value=true
  try {
    const data=(await axios.get(track.lyrics_url)).data
    if (currentTrack.value===track) lyrics.value=parseLyrics(data.lyric || data.lyrics || '')
  } catch { if (currentTrack.value===track) lyrics.value=[] }
}
function seekToLyric(time:number) { if (!audio.value) return; audio.value.currentTime=time; currentTime.value=time }
function handleShortcut(event:KeyboardEvent) { const tag=(event.target as HTMLElement | null)?.tagName; if (!currentTrack.value || ['INPUT','TEXTAREA','SELECT','BUTTON'].includes(tag || '') || (event.target as HTMLElement | null)?.isContentEditable) return; if (event.code==='Space') { event.preventDefault(); togglePlayback() } else if (event.altKey && event.code==='ArrowLeft') stepTrack(-1); else if (event.altKey && event.code==='ArrowRight') stepTrack(1) }
watch(activeLyric,async index=>{ if(index<0 || !lyricsOpen.value) return; await nextTick(); lyricsScroll.value?.querySelectorAll('button')[index]?.scrollIntoView({block:'center',behavior:'smooth'}) })
function handleAudioError() { playing.value=false; ElMessage.error('音频加载失败，文件可能已移动或浏览器不支持该格式') }
onMounted(() => window.addEventListener('keydown', handleShortcut))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleShortcut)
  if (visualizerFrame) cancelAnimationFrame(visualizerFrame)
  audio.value?.pause()
  audio.value?.removeAttribute('src')
  audio.value?.load()
  void audioContext?.close()
})
defineExpose({ playTrack, togglePlayback, currentTrack, playing })
</script>

<template>
<audio ref="audio" class="audio-player" preload="metadata" @error="handleAudioError" @play="playing=true" @pause="playing=false" @ended="stepTrack(1)" @loadedmetadata="totalTime=audio?.duration || 0" @timeupdate="currentTime=audio?.currentTime || 0"/><footer v-if="currentTrack" class="player-bar"><div class="player-now"><div class="player-cover"><img v-if="currentTrack.cover_url && !coverFailed" :src="currentTrack.cover_url" alt="" @error="coverFailed=true"><el-icon v-else><Headset/></el-icon></div><div class="player-meta"><strong>{{ currentTrack.song_name }}</strong><span>{{ currentTrack.singers }}</span></div><button v-if="currentTrack.lyrics_url" class="lyric-button" type="button" :class="{on:lyricsOpen}" title="歌词" @click="loadLyrics(true)">词</button></div><div class="player-center"><div class="transport"><button type="button" title="上一首" @click="stepTrack(-1)"><el-icon><ArrowLeftBold/></el-icon></button><button class="main-play" type="button" :title="playing ? '暂停' : '播放'" @click="togglePlayback"><el-icon><VideoPause v-if="playing"/><VideoPlay v-else/></el-icon></button><button type="button" title="下一首" @click="stepTrack(1)"><el-icon><ArrowRightBold/></el-icon></button></div><div class="seek-row"><span>{{ formatTime(currentTime) }}</span><input aria-label="播放进度" v-model.number="currentTime" type="range" min="0" :max="totalTime || 0" step="0.1" @input="seek"><span>{{ formatTime(totalTime) }}</span></div></div><div class="player-right"><canvas ref="visualizer" class="visualizer"/><el-icon><Headset/></el-icon><input aria-label="音量" v-model.number="volume" type="range" min="0" max="100" @input="setVolume"></div></footer><el-drawer v-model="lyricsOpen" title="歌词" direction="rtl" size="min(390px,92vw)" class="lyrics-drawer"><div v-if="lyrics.length" ref="lyricsScroll" class="lyrics-scroll"><button v-for="(line,index) in lyrics" :key="`${line.time}-${index}`" type="button" :class="{active:index===activeLyric}" @click="seekToLyric(line.time)">{{ line.text }}</button></div><div v-else class="drawer-empty">暂无歌词</div></el-drawer>
</template>

<style scoped>
.player-bar{position:fixed;right:16px;bottom:0;left:16px;z-index:30;display:grid;grid-template-columns:minmax(240px,1fr) minmax(440px,2.2fr) minmax(280px,1fr);gap:26px;align-items:center;max-width:1732px;min-height:92px;margin:0 auto;padding:10px 24px;border:1px solid #302a3c;border-bottom:0;border-radius:16px 16px 0 0;background:#15121df2;box-shadow:0 -14px 36px rgb(8 5 12 / 34%);backdrop-filter:blur(18px)}.player-now{display:flex;align-items:center;gap:12px;min-width:0}.player-cover{display:grid;width:54px;height:54px;flex:none;place-items:center;overflow:hidden;border-radius:9px;background:#30283a;color:#ff8a9d;font-size:22px}.player-cover img{width:100%;height:100%;object-fit:cover}.player-meta{display:flex;min-width:0;flex:1;flex-direction:column;gap:5px}.player-meta strong,.player-meta span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.player-meta strong{color:#eee8f3;font-size:14px}.player-meta span{color:#93889f;font-size:12px}.lyric-button{width:35px;height:35px;flex:none;border:1px solid #4b4057;border-radius:8px;background:transparent;color:#d9c8e3;cursor:pointer}.lyric-button.on{border-color:#fc659b;background:#4c263e;color:#fff}.player-center{display:flex;min-width:0;flex-direction:column;gap:7px}.transport{display:flex;align-items:center;justify-content:center;gap:14px}.transport button{display:grid;width:32px;height:32px;place-items:center;border:0;background:transparent;color:#bdb2ca;cursor:pointer}.transport .main-play{width:48px;height:48px;border-radius:50%;background:linear-gradient(100deg,#ffb46b,#ff6b9d);color:#251322;font-size:21px;box-shadow:0 0 24px rgb(255 107 157 / 24%)}.seek-row{display:grid;grid-template-columns:42px minmax(120px,1fr) 42px;gap:10px;align-items:center}.seek-row span{color:#8e829b;font-size:11px;text-align:center}.seek-row input,.player-right input{accent-color:#ff6b9d}.player-right{display:flex;align-items:center;justify-content:flex-end;gap:12px;color:#cfc5da}.visualizer{width:220px;height:44px;max-width:58%}.player-right input{width:92px}
.drawer-empty{display:grid;min-height:260px;place-items:center;color:var(--mf-text-muted)}
.lyrics-scroll{display:flex;height:100%;flex-direction:column;gap:2px;overflow-y:auto;padding:24px}
.lyrics-scroll button{padding:10px 0;border:0;background:transparent;color:var(--mf-text-muted);font:500 15px/1.7 'Microsoft YaHei',sans-serif;text-align:left;cursor:pointer}
.lyrics-scroll button.active{color:var(--mf-text);font-size:17px;font-weight:800}
.player-bar{background:var(--mf-surface);border-color:var(--mf-border);color:var(--mf-text);box-sizing:border-box}
.player-meta strong{color:var(--mf-text)}.player-meta span,.seek-row span{color:var(--mf-text-muted)}
.transport button,.player-right{color:var(--mf-text)}
.player-cover{background:var(--mf-surface-soft)}.lyric-button{border-color:var(--mf-border);color:var(--mf-text)}
@media(max-width:1150px){.player-bar{grid-template-columns:minmax(180px,1fr) minmax(260px,2fr) 110px;gap:14px}.visualizer{display:none}}
@media(max-width:720px){.player-bar{right:0;bottom:64px;left:0;grid-template-columns:1fr auto;gap:8px;min-height:126px;padding:10px 14px;border-right:0;border-left:0;border-radius:14px 14px 0 0}.player-now{min-width:0}.player-cover{width:44px;height:44px}.player-center{grid-column:1/-1;grid-row:2}.player-right{display:none}.transport{position:absolute;top:14px;right:14px}.transport button:not(.main-play){display:none}.transport .main-play{width:44px;height:44px}}
@media(max-width:720px){.player-now{padding-right:58px}.player-meta{min-width:32px}}
</style>
