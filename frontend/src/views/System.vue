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

const status = ref<SystemStatus | null>(null)
const loading = ref(false)
const installing = ref(false)

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

onMounted(loadStatus)
</script>

<template>
  <div class="product-page system-page" v-loading="loading">
    <div class="page-header"><div class="page-title-block"><h1>系统状态</h1><p>检查 MusicFlow 运行环境，并安装音频转换工具。</p></div><el-button @click="loadStatus">刷新状态</el-button></div>
    <el-card v-if="status" class="system-card">
      <section class="overview"><div><small>运行平台</small><strong>{{ status.platform }} · {{ status.architecture }}</strong></div><div><small>应用数据</small><strong :class="status.data_directory.writable ? 'ok' : 'bad'">{{ status.data_directory.writable ? '可写' : '不可写' }}</strong></div><div><small>音乐目录</small><strong :class="status.music_directory.available ? 'ok' : status.music_directory.configured ? 'bad' : ''">{{ status.music_directory.available ? '可访问' : status.music_directory.configured ? '未找到' : '未配置' }}</strong></div></section>
      <section class="tool"><div><h2>FFmpeg</h2><p>{{ status.ffmpeg.installed ? status.ffmpeg.version : '未安装，无法开始音频转换。' }}</p><small v-if="status.ffmpeg.path">{{ status.ffmpeg.source }} · {{ status.ffmpeg.path }}</small></div><div class="tool-action"><el-button type="primary" plain :loading="installing" @click="installFfmpeg">{{ status.ffmpeg.installed ? '安装受管版本' : '安装 FFmpeg' }}</el-button><el-tag :type="status.ffmpeg.installed ? 'success' : 'danger'">{{ status.ffmpeg.installed ? '已安装' : '未安装' }}</el-tag></div></section>
      <section class="tool"><div><h2>FFprobe</h2><p>{{ status.ffprobe.installed ? status.ffprobe.version : '未安装，无法读取音频详细信息。' }}</p><small v-if="status.ffprobe.path">{{ status.ffprobe.source }} · {{ status.ffprobe.path }}</small></div><el-tag :type="status.ffprobe.installed ? 'success' : 'danger'">{{ status.ffprobe.installed ? '已安装' : '未安装' }}</el-tag></section>
    </el-card>
  </div>
</template>

<style scoped>
.system-card { overflow: hidden; }.overview { display: grid; grid-template-columns: repeat(3, 1fr); border-bottom: 1px solid var(--mf-line); }.overview > div { display: flex; min-height: 110px; flex-direction: column; justify-content: center; gap: 9px; padding: 24px; border-right: 1px solid var(--mf-line); }.overview > div:last-child { border: 0; }.overview small, .tool small { color: var(--mf-muted); }.overview strong { color: var(--mf-ink); font-size: 17px; }.ok { color: var(--mf-green) !important; }.bad { color: #c45656 !important; }.tool { display: flex; min-height: 126px; align-items: center; justify-content: space-between; gap: 24px; padding: 24px; border-bottom: 1px solid var(--mf-line); }.tool:last-child { border: 0; }.tool h2 { margin-bottom: 7px; color: var(--mf-ink); font-size: 17px; }.tool p { margin-bottom: 7px; color: #5f6d65; font-size: 13px; }.tool small { word-break: break-all; }.tool-action { display: flex; gap: 10px; align-items: center; } @media (max-width: 700px) { .overview { grid-template-columns: 1fr; }.overview > div { min-height: auto; border-right: 0; border-bottom: 1px solid var(--mf-line); }.tool { align-items: flex-start; flex-direction: column; } }
</style>
