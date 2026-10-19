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
    <div class="page-header"><div class="page-title-block"><h1>系统状态</h1><p>管理运行依赖、musicdl 连接与 Apple Music 上传准备。</p></div><el-button @click="refreshAll">刷新状态</el-button></div>
    <el-card v-if="status" class="system-card">
      <section class="overview"><div><small>运行平台</small><strong>{{ status.platform }} · {{ status.architecture }}</strong></div><div><small>应用数据</small><strong :class="status.data_directory.writable ? 'ok' : 'bad'">{{ status.data_directory.writable ? '可写' : '不可写' }}</strong></div><div><small>音乐目录</small><strong :class="status.music_directory.available ? 'ok' : status.music_directory.configured ? 'bad' : ''">{{ status.music_directory.available ? '可访问' : status.music_directory.configured ? '未找到' : '未配置' }}</strong></div></section>
      <section class="tool"><div><h2>FFmpeg</h2><p>{{ status.ffmpeg.installed ? status.ffmpeg.version : '未安装，无法开始音频转换。' }}</p><small v-if="status.ffmpeg.path">{{ status.ffmpeg.source }} · {{ status.ffmpeg.path }}</small></div><div class="tool-action"><el-button type="primary" plain :loading="installing" @click="installFfmpeg">{{ status.ffmpeg.installed ? '安装受管版本' : '安装 FFmpeg' }}</el-button><el-tag :type="status.ffmpeg.installed ? 'success' : 'danger'">{{ status.ffmpeg.installed ? '已安装' : '未安装' }}</el-tag></div></section>
      <section class="tool"><div><h2>FFprobe</h2><p>{{ status.ffprobe.installed ? status.ffprobe.version : '未安装，无法读取音频详细信息。' }}</p><small v-if="status.ffprobe.path">{{ status.ffprobe.source }} · {{ status.ffprobe.path }}</small></div><el-tag :type="status.ffprobe.installed ? 'success' : 'danger'">{{ status.ffprobe.installed ? '已安装' : '未安装' }}</el-tag></section>
      <section class="tool musicdl-tool"><div class="musicdl-details"><h2>musicdl 服务</h2><p>配置 MusicFlow 可访问的 musicdl 地址，并检查连接与双库补齐接口。</p><div class="musicdl-form"><el-input v-model="musicdlUrl" placeholder="例如 http://musicdl-web:5000" aria-label="musicdl 服务地址"/><el-button :loading="savingMusicdl" @click="saveMusicdl">保存地址</el-button><el-button :loading="checkingMusicdl" @click="loadMusicdl">检测连接</el-button></div><small>Docker 容器中的 127.0.0.1 指向 MusicFlow 自身；请使用同网络的容器名或可访问的本地地址。</small><p v-if="musicdlStatus?.connected && !musicdlStatus.acquisition_supported" class="musicdl-warning">搜索和普通下载可连接，但当前 musicdl 缺少一键补齐所需的新版下载接口。</p><p v-else-if="musicdlStatus?.error" class="musicdl-warning">{{ musicdlStatus.error }}</p></div><el-tag v-if="musicdlStatus" :type="musicdlStatus.connected ? 'success' : 'danger'">{{ musicdlStatus.connected ? `已连接${musicdlStatus.version ? ` · ${musicdlStatus.version}` : ''}` : '未连接' }}</el-tag></section>
      <ConfigurationBackup @imported="refreshAll" />
      <section id="apple-upload" class="tool musicdl-tool" v-loading="uploadBusy"><div class="musicdl-details">
        <h2>Apple Music 服务端上传（实验）</h2>
        <p>日常上传由服务端执行，无需保持桌面电脑开机。仅支持 AAC LC M4A；部分歌曲要求的指纹尚未支持，不保证所有歌曲可上传。</p>
        <p v-if="uploadError" class="musicdl-warning">{{ uploadError }}</p>
        <template v-if="upload">
          <p v-if="!upload.supported" class="musicdl-warning">当前为桌面运行环境。授权请导入 Linux/Docker 服务端，当前页面可下载准备工具和校验算法文件。</p>
          <h3>1. 获取桌面授权</h3>
          <p>首次或授权过期时，在 Windows Apple Music 登录，下载并完整解压工具后，双击 start-authorization.cmd，按窗口提示读取并导出加密授权。首次缺少依赖时会询问是否安装。当前提供 Windows 获取工具。</p>
          <a href="/api/system/apple-upload/desktop-tools" download><el-button>下载授权工具</el-button></a>
          <h3>2. 导入加密授权</h3>
          <p>选择 account.mfup；首次另选 store.key，重新授权复用原密钥。请通过可信连接操作，并妥善保管密钥。</p>
          <div class="upload-inputs"><label>加密授权 <input type="file" accept=".mfup" @change="chooseFiles($event, 'account')" /></label><label>首次导入密钥 <input type="file" accept=".key" @change="chooseFiles($event, 'key')" /></label></div>
          <div class="tool-action"><el-button :disabled="!upload.supported || !accountFile || (!upload.key_saved && !keyFile)" @click="importUpload('authorization')">导入授权</el-button><el-tag :type="upload.authorization_saved ? 'success' : 'warning'">{{ upload.authorization_saved ? '已保存加密授权' : '授权未就绪' }}</el-tag></div>
          <h3>3. 安装算法文件</h3>
          <p>从已安装的 Apple Music 1.1540.23041.0 x64 目录选择以下四个原始文件，导入时逐一校验版本。文件不随镜像分发。</p>
          <p v-for="file in upload.files" :key="file.name">{{ file.name }} · {{ file.valid ? '校验通过' : '未就绪或版本不匹配' }}</p>
          <div class="upload-inputs"><label>算法文件 <input type="file" multiple accept=".exe,.dll" @change="chooseFiles($event, 'algorithms')" /></label><el-button :disabled="algorithmFiles.length !== 4" @click="importUpload('algorithms')">校验并安装</el-button></div>
          <h3>服务端状态</h3>
          <div class="upload-inputs"><label>上传并发数（所有目录和方案共用）<el-input-number v-model="concurrency" :min="1" :max="5" :step="1" step-strictly :precision="0" aria-label="上传并发数" /></label><el-button :loading="concurrencySaving" @click="saveConcurrency">保存上传并发</el-button></div>
          <p>正在处理 {{ upload.worker.active_count || 0 }} 首 · 排队 {{ upload.worker.queued_count || 0 }} 首 · 已保存并发 {{ upload.worker.concurrency || 1 }}。名额包含计算、上传和云端等待。</p>
          <p>安全兼容模式：并发名额用于本地成品准备；Apple 协议会话依次执行，避免同一资料库的会话冲突。</p>
          <p v-if="(upload.worker.active_count || 0) > (upload.worker.concurrency || 1)">现有任务结束后逐步降至目标并发，不打断在途上传。</p>
          <p>{{ upload.worker.online ? '上传执行器在线' : '上传执行器尚未就绪' }}。FFmpeg / FFprobe 使用上方受管依赖。</p>
          <p v-if="upload.worker.scheduler_error" class="musicdl-warning">上传执行器无法启动新任务，已暂停领取。请检查服务器可用资源并重启执行器。</p>
          <p>{{ upload.worker.server_verified_at ? `最近服务端授权验证：${new Date(upload.worker.server_verified_at * 1000).toLocaleString('zh-CN')}` : '尚未验证服务端授权，本地保存成功不代表服务端授权有效。' }}</p>
          <el-button @click="loadUpload">刷新准备状态</el-button>
        </template>
      </div></section>
    </el-card>
  </div>
</template>

<style scoped>
.page-header { padding:30px 34px; margin-bottom:18px; border:1px solid #ece8fb; border-radius:24px; background:linear-gradient(120deg,#fff 40%,#f7f3ff); }
.system-card { overflow:hidden; border:1px solid #ebe6f8 !important; border-radius:20px !important; box-shadow:0 12px 34px rgba(112,79,190,.08) !important; }.overview{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid #eeeaf8;background:#fbfaff}.overview>div{display:flex;min-height:110px;flex-direction:column;justify-content:center;gap:9px;padding:24px;border-right:1px solid #eeeaf8}.overview>div:last-child{border:0}.overview small,.tool small{color:#8f96aa}.overview strong{color:#28354d;font-size:17px}.ok{color:#24a26c!important}.bad{color:#d95c64!important}.tool{display:flex;min-height:126px;align-items:center;justify-content:space-between;gap:24px;padding:24px;border-bottom:1px solid #f0edf7}.tool:last-child{border:0}.tool h2{margin-bottom:7px;color:#2d3951;font-size:17px}.tool p{margin-bottom:7px;color:#69768d;font-size:13px}.tool small{word-break:break-all}.tool-action{display:flex;gap:10px;align-items:center}@media(max-width:700px){.overview{grid-template-columns:1fr}.overview>div{min-height:auto;border-right:0;border-bottom:1px solid #eeeaf8}.tool{align-items:flex-start;flex-direction:column}}
.musicdl-details{flex:1;min-width:0}.musicdl-form{display:flex;max-width:760px;gap:8px;margin:12px 0}.musicdl-form .el-input{flex:1}.musicdl-warning{color:#d95c64!important}.musicdl-tool{align-items:flex-start}@media(max-width:700px){.musicdl-form{flex-wrap:wrap}.musicdl-form .el-input{flex-basis:100%}}
.upload-inputs{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0}.upload-inputs label{display:flex;flex-direction:column;gap:8px;font-size:13px}.musicdl-details h3{font-size:14px;margin:20px 0 8px}
</style>
