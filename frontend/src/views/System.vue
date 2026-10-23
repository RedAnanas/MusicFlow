<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'
import ConfigurationBackup from '../components/ConfigurationBackup.vue'
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

interface UploadPreparation { supported: boolean; authorization_saved: boolean; key_saved: boolean; files: { name: string; valid: boolean }[]; worker: { online?: boolean; server_verified_at?: number; concurrency?: number; active_count?: number; queued_count?: number; scheduler_error?: string } }
const upload = ref<UploadPreparation | null>(null)
const uploadBusy = ref(false)
const algorithmFiles = ref<File[]>([])
const accountFile = ref<File | null>(null)
const keyFile = ref<File | null>(null)
const uploadError = ref('')
const concurrency = ref(1)
const concurrencySaving = ref(false)
let uploadTimer: ReturnType<typeof setInterval> | undefined
let concurrencyLoaded = false
async function refreshUploadStatus() {
  try {
    const status = await axios.get('/api/apple-music/workers/status')
    if (upload.value) upload.value.worker = status.data
    if (!concurrencyLoaded) { concurrency.value = status.data.concurrency; concurrencyLoaded = true }
    uploadError.value = ''
  } catch { uploadError.value = '上传状态刷新失败，当前显示可能已过期' }
}
async function saveConcurrency() {
  concurrencySaving.value = true
  try {
    const { data } = await axios.put('/api/apple-music/workers/concurrency', { concurrency: concurrency.value })
    if (upload.value) upload.value.worker = data
    concurrency.value = data.concurrency
    ElMessage.success(data.online ? '上传并发已保存，执行器下轮调度生效' : '上传并发已保存，执行器恢复后生效')
  } catch { ElMessage.error('上传并发保存失败，请重试') }
  finally { concurrencySaving.value = false }
}
onMounted(() => { void refreshUploadStatus(); uploadTimer = setInterval(() => { void refreshUploadStatus() }, 5000) })
onUnmounted(() => { if (uploadTimer) clearInterval(uploadTimer) })
function chooseFiles(event: Event, kind: string) {
  const files = Array.from((event.target as HTMLInputElement).files || [])
  if (kind === 'algorithms') algorithmFiles.value = files
  else if (kind === 'account') accountFile.value = files[0] || null
  else keyFile.value = files[0] || null
}
async function loadUpload() {
  try { upload.value = (await axios.get('/api/system/apple-upload')).data; uploadError.value = '' }
  catch { uploadError.value = '无法读取上传准备状态，请重试' }
}
async function importUpload(kind: 'algorithms' | 'authorization') {
  const data = new FormData()
  if (kind === 'algorithms') algorithmFiles.value.forEach(file => data.append('files', file))
  else {
    if (!accountFile.value) return
    data.append('account', accountFile.value)
    if (keyFile.value) data.append('key', keyFile.value)
  }
  uploadBusy.value = true
  try {
    upload.value = (await axios.post(`/api/system/apple-upload/${kind}`, data)).data
    ElMessage.success(kind === 'algorithms' ? '算法文件已校验并安装' : '加密授权已导入，请刷新执行器状态；本地保存不代表服务端验证通过')
  } catch (error: any) { ElMessage.error(error.response?.data?.detail || '导入失败') }
  finally { uploadBusy.value = false }
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
  void loadUpload()
}

onMounted(refreshAll)
</script>

<template>
  <div class="product-page system-page" v-loading="loading">
    <header class="page-header">
      <div class="page-title-block"><span class="section-label">运行环境与服务</span><h1>系统设置</h1><p>管理运行依赖、musicdl 连接与 Apple Music 上传准备。</p></div>
      <el-button @click="refreshAll"><el-icon><Refresh /></el-icon>刷新状态</el-button>
    </header>
    <template v-if="status">
      <section class="overview" aria-label="运行概况">
        <div class="system-card overview-card"><el-icon class="overview-icon"><Monitor /></el-icon><div><small>运行平台</small><strong>{{ status.platform }} · {{ status.architecture }}</strong></div></div>
        <div class="system-card overview-card"><el-icon class="overview-icon"><FolderOpened /></el-icon><div><small>应用数据</small><strong :class="status.data_directory.writable ? 'ok' : 'bad'">{{ status.data_directory.writable ? '可写' : '不可写' }}</strong></div></div>
        <div class="system-card overview-card"><el-icon class="overview-icon"><Headset /></el-icon><div><small>音乐目录</small><strong :class="status.music_directory.available ? 'ok' : status.music_directory.configured ? 'bad' : ''">{{ status.music_directory.available ? '可访问' : status.music_directory.configured ? '未找到' : '未配置' }}</strong></div></div>
      </section>

      <div class="settings-grid">
        <section class="system-card settings-panel">
          <header class="panel-heading"><div><span class="section-label">音频处理</span><h2>运行依赖</h2><p>转换与音频信息读取共用受管工具。</p></div><el-icon class="panel-icon"><Tools /></el-icon></header>
          <div class="tool">
            <div class="tool-heading"><h3>FFmpeg</h3><el-tag :type="status.ffmpeg.installed ? 'success' : 'danger'">{{ status.ffmpeg.installed ? '已安装' : '未安装' }}</el-tag></div>
            <p class="tool-version">{{ status.ffmpeg.installed ? status.ffmpeg.version : '未安装，无法开始音频转换。' }}</p>
            <small v-if="status.ffmpeg.path">{{ status.ffmpeg.source }} · {{ status.ffmpeg.path }}</small>
            <el-button class="install-action" plain :loading="installing" @click="installFfmpeg">{{ status.ffmpeg.installed ? '安装受管版本' : '安装 FFmpeg' }}</el-button>
          </div>
          <div class="tool">
            <div class="tool-heading"><h3>FFprobe</h3><el-tag :type="status.ffprobe.installed ? 'success' : 'danger'">{{ status.ffprobe.installed ? '已安装' : '未安装' }}</el-tag></div>
            <p class="tool-version">{{ status.ffprobe.installed ? status.ffprobe.version : '未安装，无法读取音频详细信息。' }}</p>
            <small v-if="status.ffprobe.path">{{ status.ffprobe.source }} · {{ status.ffprobe.path }}</small>
          </div>
        </section>

        <section class="system-card settings-panel">
          <header class="panel-heading"><div><span class="section-label">下载与补齐</span><h2>musicdl 服务</h2><p>配置服务地址，检测连接与双库补齐接口。</p></div><el-icon class="panel-icon"><Connection /></el-icon></header>
          <div class="connection-status"><span>连接状态</span><el-tag v-if="musicdlStatus" :type="musicdlStatus.connected ? 'success' : 'danger'">{{ musicdlStatus.connected ? `已连接${musicdlStatus.version ? ` · ${musicdlStatus.version}` : ''}` : '未连接' }}</el-tag><span v-else>检测中</span></div>
          <label class="field-label" for="musicdl-address">服务地址</label>
          <div class="musicdl-form"><el-input id="musicdl-address" v-model="musicdlUrl" placeholder="例如 http://musicdl-web:5000" aria-label="musicdl 服务地址" /><div class="tool-action"><el-button type="primary" :loading="savingMusicdl" @click="saveMusicdl">保存地址</el-button><el-button :loading="checkingMusicdl" @click="loadMusicdl">检测连接</el-button></div></div>
          <p class="field-help">Docker 容器中的 127.0.0.1 指向 MusicFlow 自身；请使用同网络的容器名或可访问的本地地址。</p>
          <p v-if="musicdlStatus?.connected && !musicdlStatus.acquisition_supported" class="musicdl-warning">搜索和普通下载可连接，但当前 musicdl 缺少一键补齐所需的新版下载接口。</p>
          <p v-else-if="musicdlStatus?.error" class="musicdl-warning">{{ musicdlStatus.error }}</p>
        </section>
      </div>

      <section id="apple-upload" class="system-card settings-panel upload-panel" v-loading="uploadBusy">
        <header class="panel-heading"><div><span class="section-label">Apple Music</span><h2>服务端上传 <el-tag size="small" type="info">实验功能</el-tag></h2><p>日常上传由服务端执行，无需保持桌面电脑开机。</p></div><el-button @click="loadUpload">刷新准备状态</el-button></header>
        <p class="field-help upload-notice">仅支持 AAC LC M4A；部分歌曲要求的指纹尚未支持，不保证所有歌曲可上传。</p>
        <p v-if="uploadError" class="musicdl-warning" role="alert">{{ uploadError }}</p>
        <template v-if="upload">
          <p v-if="!upload.supported" class="musicdl-warning">当前为桌面运行环境。授权请导入 Linux/Docker 服务端，当前页面可下载准备工具和校验算法文件。</p>
          <div class="worker-panel">
            <div class="worker-status"><h3>执行器状态</h3><el-tag :type="upload.worker.online ? 'success' : 'warning'">{{ upload.worker.online ? '在线' : '尚未就绪' }}</el-tag></div>
            <div class="worker-metrics"><div><span>正在处理</span><strong>{{ upload.worker.active_count || 0 }}<small>首</small></strong></div><div><span>排队等待</span><strong>{{ upload.worker.queued_count || 0 }}<small>首</small></strong></div><div><span>已保存并发</span><strong>{{ upload.worker.concurrency || 1 }}<small>首</small></strong></div></div>
            <div class="concurrency-control"><label for="upload-concurrency">上传并发数<span>所有目录和方案共用</span></label><div class="tool-action"><el-input-number id="upload-concurrency" v-model="concurrency" :min="1" :max="5" :step="1" step-strictly :precision="0" aria-label="上传并发数" /><el-button :loading="concurrencySaving" @click="saveConcurrency">保存上传并发</el-button></div></div>
            <p class="field-help">名额包含计算、上传和云端等待。并发大于 1 时，多首歌曲可提前解析音频、提取歌词封面并计算指纹；Apple 上传会话仍逐首执行。并发为 1 时按需计算指纹，避免额外准备。</p>
            <p v-if="(upload.worker.active_count || 0) > (upload.worker.concurrency || 1)" class="field-help">现有任务结束后逐步降至目标并发，不打断在途上传。</p>
            <p v-if="upload.worker.scheduler_error" class="musicdl-warning" role="alert">上传执行器无法启动新任务，已暂停领取。请检查服务器可用资源并重启执行器。</p>
            <p class="verification-time">{{ upload.worker.server_verified_at ? `最近服务端授权验证：${new Date(upload.worker.server_verified_at * 1000).toLocaleString('zh-CN')}` : '尚未验证服务端授权，本地保存成功不代表服务端授权有效。' }} FFmpeg / FFprobe 使用上方受管依赖。</p>
          </div>

          <div class="preparation-heading"><h3>上传准备</h3><p>首次配置或授权过期时，按以下步骤准备。</p></div>
          <div class="preparation-grid">
            <section class="preparation-step">
              <div class="step-heading"><el-icon><Download /></el-icon><h3>1. 获取桌面授权</h3></div>
              <p>首次或授权过期时，在 Windows Apple Music 登录，下载并完整解压工具后，双击 start-authorization.cmd，按窗口提示读取并导出加密授权。首次缺少依赖时会询问是否安装。当前提供 Windows 获取工具。</p>
              <a href="/api/system/apple-upload/desktop-tools" download><el-button>下载授权工具</el-button></a>
            </section>
            <section class="preparation-step">
              <div class="step-heading"><el-icon><Key /></el-icon><h3>2. 导入加密授权</h3></div>
              <p>选择 account.mfup；首次另选 store.key，重新授权复用原密钥。请通过可信连接操作，并妥善保管密钥。</p>
              <div class="upload-inputs"><label>加密授权<input type="file" accept=".mfup" @change="chooseFiles($event, 'account')" /></label><label>首次导入密钥<input type="file" accept=".key" @change="chooseFiles($event, 'key')" /></label></div>
              <div class="tool-action"><el-button :disabled="!upload.supported || !accountFile || (!upload.key_saved && !keyFile)" @click="importUpload('authorization')">导入授权</el-button><el-tag :type="upload.authorization_saved ? 'success' : 'warning'">{{ upload.authorization_saved ? '已保存加密授权' : '授权未就绪' }}</el-tag></div>
            </section>
            <section class="preparation-step">
              <div class="step-heading"><el-icon><Tools /></el-icon><h3>3. 安装算法文件</h3></div>
              <p>从已安装的 Apple Music 1.1540.23041.0 x64 目录选择以下四个原始文件，导入时逐一校验版本。文件不随镜像分发。</p>
              <ul class="algorithm-files"><li v-for="file in upload.files" :key="file.name"><span>{{ file.name }}</span><el-tag size="small" :type="file.valid ? 'success' : 'warning'">{{ file.valid ? '校验通过' : '未就绪或版本不匹配' }}</el-tag></li></ul>
              <div class="upload-inputs"><label>算法文件<input type="file" multiple accept=".exe,.dll" @change="chooseFiles($event, 'algorithms')" /></label></div>
              <el-button :disabled="algorithmFiles.length !== 4" @click="importUpload('algorithms')">校验并安装</el-button>
            </section>
          </div>
        </template>
      </section>
      <ConfigurationBackup class="system-card backup-panel" @imported="refreshAll" />
    </template>
  </div>
</template>

<style scoped>
.system-page {
  --el-color-primary: #7558d9;
  --el-color-primary-light-3: #8064d8;
  --el-color-primary-light-5: #bca7ef;
  --el-color-primary-light-7: #d8ccf7;
  --el-color-primary-light-9: var(--mf-nav-hover);
  --el-color-primary-dark-2: #6044b8;
  --el-bg-color: var(--mf-surface);
  --el-fill-color-blank: var(--mf-surface-muted);
  --el-text-color-primary: var(--mf-text);
  --el-text-color-regular: var(--mf-text);
  --el-text-color-secondary: var(--mf-text-muted);
  --el-border-color: var(--mf-border);
  --el-border-color-light: var(--mf-border);
  --el-border-color-lighter: var(--mf-border);
  display: grid;
  gap: 20px;
}
.system-page h1, .system-page h2, .system-page h3 { margin: 0; color: var(--mf-text); }
.system-page p { margin: 8px 0 0; color: var(--mf-text-muted); font-size: 13px; line-height: 1.75; }
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 28px 30px; border: 1px solid var(--mf-border); border-radius: 24px; background: var(--mf-surface); }
.page-header h1 { margin: 7px 0 0; font-size: 30px; letter-spacing: -.6px; }
.section-label { color: var(--el-color-primary); font-size: 12px; font-weight: 700; letter-spacing: .08em; }
.system-card { min-width: 0; border: 1px solid var(--mf-border); border-radius: 20px; background: var(--mf-surface); box-shadow: 0 12px 30px rgb(35 24 78 / 5%); }
.overview { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.overview-card { display: flex; align-items: center; gap: 16px; padding: 22px 24px; }
.overview-icon { width: 46px; height: 46px; flex: 0 0 46px; border-radius: 14px; background: var(--mf-nav-hover); color: var(--el-color-primary); font-size: 23px; }
.overview-card > div { display: grid; gap: 7px; }
.overview small { color: var(--mf-text-muted); font-size: 12px; }
.overview strong { font-size: 18px; }
.ok { color: var(--el-color-success) !important; }.bad { color: var(--el-color-danger) !important; }
.settings-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: stretch; }
.settings-panel { padding: 24px; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 20px; }
.panel-heading > div { min-width: 0; }.panel-heading h2 { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 7px; font-size: 19px; }
.panel-icon { color: var(--el-color-primary); font-size: 24px; }.panel-heading > .el-button { flex-shrink: 0; }
.tool { padding: 17px 0; border-top: 1px solid var(--mf-border); }.tool:last-child { padding-bottom: 0; }
.tool-heading { display: flex; align-items: center; justify-content: space-between; gap: 14px; }.tool h3, .system-page h3 { font-size: 14px; }
.tool-version { overflow-wrap: anywhere; }.tool small { display: block; margin-top: 5px; color: var(--mf-text-muted); font-size: 12px; overflow-wrap: anywhere; }.install-action { margin-top: 14px; }
.tool-action { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }.tool-action :deep(.el-button + .el-button) { margin-left: 0; }
.connection-status { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; margin-bottom: 22px; border: 1px solid var(--mf-border); border-radius: 12px; background: var(--mf-surface-muted); color: var(--mf-text-muted); font-size: 13px; }
.field-label { display: block; margin-bottom: 9px; font-size: 13px; font-weight: 600; }.musicdl-form { display: grid; gap: 12px; }.musicdl-form .tool-action { justify-content: flex-end; }
.field-help, .verification-time { font-size: 12px !important; }.musicdl-warning { padding: 12px 14px; border: 1px solid var(--el-color-warning-light-5); border-radius: 10px; background: var(--el-color-warning-light-9); color: var(--el-color-warning) !important; overflow-wrap: anywhere; }
.upload-panel .panel-heading { margin-bottom: 10px; }.upload-notice { margin-bottom: 20px !important; }
.worker-panel { padding: 20px; border: 1px solid var(--mf-border); border-radius: 16px; background: var(--mf-surface-muted); }
.worker-status { display: flex; align-items: center; gap: 12px; }.worker-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin: 20px 0; }
.worker-metrics > div { display: grid; gap: 8px; padding-right: 16px; border-right: 1px solid var(--mf-border); }.worker-metrics > div:last-child { border: 0; }
.worker-metrics span { color: var(--mf-text-muted); font-size: 12px; }.worker-metrics strong { color: var(--mf-text); font-size: 28px; font-variant-numeric: tabular-nums; }.worker-metrics small { margin-left: 7px; color: var(--mf-text-muted); font-size: 12px; font-weight: 400; }
.concurrency-control { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; padding-top: 18px; border-top: 1px solid var(--mf-border); }.concurrency-control label { font-size: 13px; font-weight: 600; }.concurrency-control label span { display: block; margin-top: 5px; color: var(--mf-text-muted); font-size: 12px; font-weight: 400; }.concurrency-control .el-input-number { width: 144px; }
.verification-time { padding-top: 12px; margin-top: 14px !important; border-top: 1px solid var(--mf-border); }
.preparation-heading { margin: 24px 0 16px; }.preparation-heading p { margin-top: 5px; font-size: 12px; }
.preparation-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }.preparation-step { min-width: 0; padding: 20px; border: 1px solid var(--mf-border); border-radius: 14px; }
.step-heading { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }.step-heading .el-icon { color: var(--el-color-primary); font-size: 20px; }.preparation-step > p { margin-bottom: 16px; font-size: 12px; }.preparation-step a { display: inline-block; }
.upload-inputs { display: grid; gap: 14px; margin: 16px 0; }.upload-inputs label { display: grid; gap: 8px; min-width: 0; color: var(--mf-text-muted); font-size: 12px; }
.system-page input[type=file] { width: 100%; min-width: 0; font-size: 12px; color: var(--mf-text-muted); }
.system-page input[type=file]::file-selector-button { padding: 7px 11px; margin-right: 9px; border: 1px solid var(--mf-border); border-radius: 8px; background: var(--mf-surface-muted); color: var(--mf-text); font: inherit; cursor: pointer; }
.system-page input[type=file]:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 4px; }
.algorithm-files { padding: 0; margin: 16px 0; list-style: none; }.algorithm-files li { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 7px; padding: 8px 0; border-bottom: 1px solid var(--mf-border); }.algorithm-files li > span { min-width: 0; color: var(--mf-text-muted); font-size: 12px; overflow-wrap: anywhere; }
.system-page :deep(.el-button .el-icon) { margin-right: 6px; }.system-page :deep(.el-tag) { flex-shrink: 0; }.backup-panel { margin: 0; }
.system-page :deep(.el-button > span), .system-page :deep(.el-tag > span) { color: inherit; }
.system-page :deep(.el-tag) { color: var(--el-tag-text-color); }
@media (max-width: 1100px) { .preparation-grid { grid-template-columns: 1fr; }.preparation-step { padding: 20px; }.upload-inputs { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) { .system-page { gap: 14px; }.page-header { padding: 22px; flex-wrap: wrap; }.page-header h1 { font-size: 26px; }.overview, .settings-grid { grid-template-columns: 1fr; gap: 12px; }.overview-card { padding: 18px 20px; }.settings-panel { padding: 20px; }.panel-heading { flex-wrap: wrap; }.worker-panel { padding: 16px; }.worker-metrics { gap: 10px; }.worker-metrics strong { font-size: 24px; }.concurrency-control .tool-action { width: 100%; }.upload-inputs { grid-template-columns: 1fr; }.preparation-step { padding: 16px; } }
</style>
