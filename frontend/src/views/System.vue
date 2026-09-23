<script setup lang="ts">
import { onMounted, ref } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'

interface ToolStatus { installed: boolean; source: string; path: string | null; version: string | null }
interface SystemStatus {
  platform: string
  architecture: string
  ffmpeg: ToolStatus
  ffprobe: ToolStatus
  data_directory: { path: string; writable: boolean }
  music_directory: { path: string | null; configured: boolean; available: boolean }
}
interface MusicdlStatus {
  base_url: string
  connected: boolean
  version: string | null
  acquisition_supported: boolean
  error: string | null
}

const status = ref<SystemStatus | null>(null)
const loading = ref(false)
const installing = ref(false)
const musicdlStatus = ref<MusicdlStatus | null>(null)
const musicdlUrl = ref('')
const checkingMusicdl = ref(false)
const savingMusicdl = ref(false)

async function loadStatus() {
  loading.value = true
  try {
    status.value = (await axios.get('/api/system/')).data
  } catch {
    ElMessage.error('无法获取系统状态')
  } finally {
    loading.value = false
  }
}

async function installFfmpeg() {
  installing.value = true
  try {
    status.value = (await axios.post('/api/system/ffmpeg/install')).data
    ElMessage.success('FFmpeg 已安装并通过校验')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || 'FFmpeg 安装失败')
  } finally {
    installing.value = false
  }
}

async function loadMusicdl() {
  checkingMusicdl.value = true
  try {
    musicdlStatus.value = (await axios.get<MusicdlStatus>('/api/system/musicdl')).data
    musicdlUrl.value = musicdlStatus.value.base_url
  } catch {
    ElMessage.error('无法检查 musicdl 连接')
  } finally {
    checkingMusicdl.value = false
  }
}

async function saveMusicdl() {
  savingMusicdl.value = true
  try {
    await axios.put('/api/system/musicdl', { base_url: musicdlUrl.value })
    ElMessage.success('musicdl 地址已保存')
    await loadMusicdl()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '保存 musicdl 地址失败')
  } finally {
    savingMusicdl.value = false
  }
}

function refreshAll() {
  void loadStatus()
  void loadMusicdl()
}

onMounted(refreshAll)
</script>

<template>
  <div class="product-page system-page" v-loading="loading">
    <div class="page-header"><div class="page-title-block"><h1>系统状态</h1><p>检查运行环境、musicdl 连接，并安装音频转换工具。</p></div><el-button @click="refreshAll">刷新状态</el-button></div>
    <el-card v-if="status" class="system-card">
      <section class="overview"><div><small>运行平台</small><strong>{{ status.platform }} · {{ status.architecture }}</strong></div><div><small>应用数据</small><strong :class="status.data_directory.writable ? 'ok' : 'bad'">{{ status.data_directory.writable ? '可写' : '不可写' }}</strong></div><div><small>音乐目录</small><strong :class="status.music_directory.available ? 'ok' : status.music_directory.configured ? 'bad' : ''">{{ status.music_directory.available ? '可访问' : status.music_directory.configured ? '未找到' : '未配置' }}</strong></div></section>
      <section class="tool"><div><h2>FFmpeg</h2><p>{{ status.ffmpeg.installed ? status.ffmpeg.version : '未安装，无法开始音频转换。' }}</p><small v-if="status.ffmpeg.path">{{ status.ffmpeg.source }} · {{ status.ffmpeg.path }}</small></div><div class="tool-action"><el-button type="primary" plain :loading="installing" @click="installFfmpeg">{{ status.ffmpeg.installed ? '安装受管版本' : '安装 FFmpeg' }}</el-button><el-tag :type="status.ffmpeg.installed ? 'success' : 'danger'">{{ status.ffmpeg.installed ? '已安装' : '未安装' }}</el-tag></div></section>
      <section class="tool"><div><h2>FFprobe</h2><p>{{ status.ffprobe.installed ? status.ffprobe.version : '未安装，无法读取音频详细信息。' }}</p><small v-if="status.ffprobe.path">{{ status.ffprobe.source }} · {{ status.ffprobe.path }}</small></div><el-tag :type="status.ffprobe.installed ? 'success' : 'danger'">{{ status.ffprobe.installed ? '已安装' : '未安装' }}</el-tag></section>
      <section class="tool musicdl-tool"><div class="musicdl-details"><h2>musicdl 服务</h2><p>配置 MusicFlow 可访问的 musicdl 地址，并检查连接与双库补齐接口。</p><div class="musicdl-form"><el-input v-model="musicdlUrl" placeholder="例如 http://musicdl-web:5000" aria-label="musicdl 服务地址"/><el-button :loading="savingMusicdl" @click="saveMusicdl">保存地址</el-button><el-button :loading="checkingMusicdl" @click="loadMusicdl">检测连接</el-button></div><small>Docker 容器中的 127.0.0.1 指向 MusicFlow 自身；请使用同网络的容器名或可访问的本地地址。</small><p v-if="musicdlStatus?.connected && !musicdlStatus.acquisition_supported" class="musicdl-warning">搜索和普通下载可连接，但当前 musicdl 缺少一键补齐所需的新版下载接口。</p><p v-else-if="musicdlStatus?.error" class="musicdl-warning">{{ musicdlStatus.error }}</p></div><el-tag v-if="musicdlStatus" :type="musicdlStatus.connected ? 'success' : 'danger'">{{ musicdlStatus.connected ? `已连接${musicdlStatus.version ? ` · ${musicdlStatus.version}` : ''}` : '未连接' }}</el-tag></section>
    </el-card>
  </div>
</template>

<style scoped>
.page-header { padding:30px 34px; margin-bottom:18px; border:1px solid #ece8fb; border-radius:24px; background:linear-gradient(120deg,#fff 40%,#f7f3ff); }
.system-card { overflow:hidden; border:1px solid #ebe6f8 !important; border-radius:20px !important; box-shadow:0 12px 34px rgba(112,79,190,.08) !important; }.overview{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid #eeeaf8;background:#fbfaff}.overview>div{display:flex;min-height:110px;flex-direction:column;justify-content:center;gap:9px;padding:24px;border-right:1px solid #eeeaf8}.overview>div:last-child{border:0}.overview small,.tool small{color:#8f96aa}.overview strong{color:#28354d;font-size:17px}.ok{color:#24a26c!important}.bad{color:#d95c64!important}.tool{display:flex;min-height:126px;align-items:center;justify-content:space-between;gap:24px;padding:24px;border-bottom:1px solid #f0edf7}.tool:last-child{border:0}.tool h2{margin-bottom:7px;color:#2d3951;font-size:17px}.tool p{margin-bottom:7px;color:#69768d;font-size:13px}.tool small{word-break:break-all}.tool-action{display:flex;gap:10px;align-items:center}@media(max-width:700px){.overview{grid-template-columns:1fr}.overview>div{min-height:auto;border-right:0;border-bottom:1px solid #eeeaf8}.tool{align-items:flex-start;flex-direction:column}}
.musicdl-details{flex:1;min-width:0}.musicdl-form{display:flex;max-width:760px;gap:8px;margin:12px 0}.musicdl-form .el-input{flex:1}.musicdl-warning{color:#d95c64!important}.musicdl-tool{align-items:flex-start}@media(max-width:700px){.musicdl-form{flex-wrap:wrap}.musicdl-form .el-input{flex-basis:100%}}
</style>
