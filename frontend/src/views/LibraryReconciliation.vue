<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import ServerFileBrowser from '../components/ServerFileBrowser.vue'

type ReconciliationStatus = 'both' | 'nas_only' | 'apple_only' | 'review'

interface Snapshot {
  id: string
  imported_at: string
  source_filename: string
  row_count: number
  catalog_count: number
  uploaded_count: number
  unknown_count: number
  isrc_count: number
}

interface TrackSide {
  id?: string
  track_key?: string
  apple_id?: string
  apple_kind?: 'catalog' | 'uploaded' | 'unknown'
  path?: string
  filename?: string
  title?: string
  artist?: string
  album?: string
  isrc?: string
  format?: string
}

interface ReconciliationEntry {
  id: string
  status: ReconciliationStatus
  match_reason: string
  apple: TrackSide | null
  local: TrackSide | null
  candidates: TrackSide[]
}

interface ReconciliationResponse {
  snapshot: Snapshot
  summary: Record<ReconciliationStatus, number>
  total: number
  entries: ReconciliationEntry[]
}

interface MediaLibrarySource {
  id: string
  path: string
  exists: boolean
  is_directory: boolean
}

interface AppleIncrementalEntry {
  id: string
  title: string
  artist: string
  album: string
  isrc?: string
  apple_id?: string
  source: 'manual' | 'catalog' | 'handoff'
  verification_status: 'pending' | 'confirmed'
  updated_at: string
}

const fileInput = ref<HTMLInputElement>()
const snapshot = ref<Snapshot | null>(null)
const ageDays = ref<number | null>(null)
const isStale = ref(true)
const loading = ref(false)
const uploading = ref(false)
const statusFilter = ref<ReconciliationStatus | ''>('')
const search = ref('')
const currentPage = ref(1)
const pageSize = ref(100)
const total = ref(0)
const entries = ref<ReconciliationEntry[]>([])
const summary = ref<Record<ReconciliationStatus, number>>({ both: 0, nas_only: 0, apple_only: 0, review: 0 })
const selectedCandidates = reactive<Record<string, string>>({})
const selectedReviews = ref<ReconciliationEntry[]>([])
const selectedReviewCount = computed(() => selectedReviews.value.filter(entry => entry.status === 'review').length)
const mediaSources = ref<MediaLibrarySource[]>([])
const showMediaBrowser = ref(false)
const mediaSourcesLoading = ref(false)
const incrementalEntries = ref<AppleIncrementalEntry[]>([])
const incrementalOpen = ref(false)
const incrementalSaving = ref(false)
const incrementalForm = reactive({ title: '', artist: '', album: '', isrc: '', apple_id: '' })

const snapshotDescription = computed(() => {
  if (!snapshot.value) return '尚未导入 Apple Music 资料库快照'
  return `${snapshot.value.source_filename} · ${snapshot.value.row_count} 首 · ${formatTime(snapshot.value.imported_at)}`
})

const statusOptions: Array<{ value: ReconciliationStatus | '', label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'both', label: '双库都有' },
  { value: 'nas_only', label: '仅飞牛有' },
  { value: 'apple_only', label: '仅 Apple Music 有' },
  { value: 'review', label: '待确认' },
]

const statusLabels: Record<ReconciliationStatus, string> = {
  both: '双库都有',
  nas_only: '仅飞牛有',
  apple_only: '仅 Apple Music 有',
  review: '待确认',
}

const reasonLabels: Record<string, string> = {
  isrc: 'ISRC 一致',
  metadata_exact: '歌名、歌手和专辑一致',
  title_artist: '歌名和歌手一致',
  title_artist_album_diff: '歌名和歌手一致（专辑不同）',
  title_artist_similar: '歌名一致，歌手名相似，等待确认',
  title_subject_artist_compatible: '歌名主体一致、歌手一致或相似，等待确认',
  fuzzy: '名称近似，等待确认',
  manual_confirmed: '人工确认',
  no_match: '未找到匹配',
}

function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function displayTitle(side: TrackSide | null) {
  return side?.title || side?.filename || '—'
}

function displaySubtitle(side: TrackSide | null) {
  if (!side) return '—'
  return [side.artist, side.album].filter(Boolean).join(' · ') || side.path || '—'
}

function displayLocal(entry: ReconciliationEntry) {
  return entry.local || entry.candidates.find(candidate => candidate.id === selectedCandidates[entry.id]) || null
}

function selectableReview(row: ReconciliationEntry) {
  return row.status === 'review'
}

async function loadStatus() {
  const response = await axios.get('/api/apple-library/status')
  snapshot.value = response.data.snapshot
  ageDays.value = response.data.age_days
  isStale.value = response.data.is_stale
}

async function loadIncrementalEntries() {
  incrementalEntries.value = (await axios.get<AppleIncrementalEntry[]>('/api/apple-library/entries')).data
}

async function addIncrementalEntry() {
  if (!incrementalForm.title.trim() || !incrementalForm.artist.trim()) {
    ElMessage.warning('请填写歌名和歌手')
    return
  }
  incrementalSaving.value = true
  try {
    await axios.post('/api/apple-library/entries', { ...incrementalForm, source: 'manual' })
    Object.assign(incrementalForm, { title: '', artist: '', album: '', isrc: '', apple_id: '' })
    incrementalOpen.value = false
    await loadIncrementalEntries()
    ElMessage.success('已添加 Apple Music 待确认记录')
  } catch (error) {
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '添加记录失败' : '添加记录失败')
  } finally {
    incrementalSaving.value = false
  }
}

async function deleteIncrementalEntry(entry: AppleIncrementalEntry) {
  try {
    await ElMessageBox.confirm(`删除“${entry.title} · ${entry.artist}”的增量记录吗？`, '删除记录', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
    await axios.delete(`/api/apple-library/entries/${entry.id}`)
    await loadIncrementalEntries()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '删除记录失败' : '删除记录失败')
  }
}

async function loadMediaSources() {
  mediaSourcesLoading.value = true
  try {
    mediaSources.value = (await axios.get<MediaLibrarySource[]>('/api/library/media-sources')).data
  } finally {
    mediaSourcesLoading.value = false
  }
}

async function addMediaSources(paths: string[]) {
  try {
    await axios.post('/api/library/media-sources', { paths })
    await loadMediaSources()
    ElMessage.success('媒体库文件夹已添加，正在读取整理后的媒体库')
    await loadReconciliation(true)
  } catch (error) {
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '添加媒体库失败' : '添加媒体库失败')
  }
}

async function removeMediaSource(source: MediaLibrarySource) {
  try {
    await ElMessageBox.confirm(`停止用于对账读取“${source.path}”吗？不会删除其中的媒体文件。`, '移除媒体库', {
      confirmButtonText: '停止读取', cancelButtonText: '取消', type: 'warning',
    })
    await axios.delete(`/api/library/media-sources/${source.id}`)
    await loadMediaSources()
    if (mediaSources.value.length) await loadReconciliation(true)
    else {
      entries.value = []
      total.value = 0
      summary.value = { both: 0, nas_only: 0, apple_only: 0, review: 0 }
    }
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '移除媒体库失败' : '移除媒体库失败')
  }
}

async function loadReconciliation(refreshLocal = false) {
  if (!snapshot.value) return
  loading.value = true
  try {
    const response = await axios.get<ReconciliationResponse>('/api/library/reconciliation', {
      params: {
        status: statusFilter.value || undefined,
        search: search.value.trim() || undefined,
        refresh_local: refreshLocal,
        offset: (currentPage.value - 1) * pageSize.value,
        limit: pageSize.value,
      },
    })
    entries.value = response.data.entries
    selectedReviews.value = []
    summary.value = response.data.summary
    total.value = response.data.total
    for (const entry of entries.value) {
      if (entry.status === 'review' && entry.candidates.length) {
        selectedCandidates[entry.id] = entry.candidates[0].id || ''
      }
    }
  } catch (error) {
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '对账失败' : '对账失败')
  } finally {
    loading.value = false
  }
}

function chooseCsv() {
  fileInput.value?.click()
}

async function uploadCsv(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const response = await axios.post('/api/apple-library/snapshots', form)
    ElMessage.success(response.data.created ? 'Apple Music 快照导入成功' : '相同快照已导入，无需重复创建')
    currentPage.value = 1
    await loadStatus()
    await loadIncrementalEntries()
    await loadReconciliation(true)
  } catch (error) {
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '快照导入失败' : '快照导入失败')
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function applyFilters() {
  currentPage.value = 1
  await loadReconciliation()
}

async function saveDecision(entry: ReconciliationEntry, decision: 'confirmed' | 'rejected') {
  const localFileId = selectedCandidates[entry.id]
  const appleTrackKey = entry.apple?.track_key
  if (!localFileId || !appleTrackKey) {
    ElMessage.warning('请先选择一个本地候选曲目')
    return
  }
  await axios.post('/api/library/matches', {
    local_file_id: localFileId,
    apple_track_key: appleTrackKey,
    decision,
  })
  ElMessage.success(decision === 'confirmed' ? '匹配已确认' : '候选已排除')
  await loadReconciliation()
}

async function batchSave(decision: 'confirmed' | 'rejected') {
  const matches = selectedReviews.value
    .filter(entry => entry.status === 'review')
    .map(entry => ({
      local_file_id: selectedCandidates[entry.id],
      apple_track_key: entry.apple?.track_key,
      decision,
    }))
  if (!matches.length) return
  if (matches.some(match => !match.local_file_id || !match.apple_track_key)) {
    ElMessage.warning('请先为每条选中的待确认记录选择本地候选曲目')
    return
  }
  await axios.post('/api/library/matches/batch', { matches })
  ElMessage.success(decision === 'confirmed' ? `已批量确认 ${matches.length} 条匹配` : `已批量排除 ${matches.length} 条候选`)
  await loadReconciliation()
}

async function deleteSnapshot() {
  if (!snapshot.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除“${snapshot.value.source_filename}”及其导入数据吗？不会删除飞牛本地音乐文件。`,
      '删除 Apple Music CSV 快照',
      { confirmButtonText: '删除快照', cancelButtonText: '取消', type: 'warning' },
    )
    await axios.delete(`/api/apple-library/snapshots/${snapshot.value.id}`)
    snapshot.value = null
    entries.value = []
    total.value = 0
    summary.value = { both: 0, nas_only: 0, apple_only: 0, review: 0 }
    ElMessage.success('Apple Music CSV 快照已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '删除快照失败' : '删除快照失败')
  }
}

async function handoffLocal(entry: ReconciliationEntry) {
  if (!entry.local?.id) return
  try {
    await axios.post('/api/acquisitions', {
      local_file_id: entry.local.id,
      desired_nas: false,
      desired_apple: true,
    })
    ElMessage.success('已创建 Apple Music 补齐任务，可在“发现音乐”查看进度')
  } catch (error) {
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '创建补齐任务失败' : '创建补齐任务失败')
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await loadStatus()
    await loadMediaSources()
    await loadIncrementalEntries()
    if (snapshot.value && mediaSources.value.length) await loadReconciliation()
  } catch {
    ElMessage.error('读取资料库状态失败')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="reconciliation-page product-page">
    <section class="page-heading">
      <div>
        <p class="eyebrow">LIBRARY RECONCILIATION</p>
        <h1>资料库对账</h1>
        <p>对比飞牛本地音乐与 Apple Music 快照，只处理真正缺少的曲目。</p>
      </div>
      <div class="heading-actions">
        <input ref="fileInput" class="file-input" type="file" accept=".csv,text/csv" @change="uploadCsv" />
        <el-button :loading="uploading" @click="chooseCsv">导入 Apple Music CSV</el-button>
        <el-button @click="incrementalOpen = true">添加 Apple Music 记录</el-button>
        <el-button type="primary" :disabled="!snapshot" :loading="loading" @click="loadReconciliation(true)">重新扫描本地库</el-button>
        <el-button v-if="snapshot" type="danger" plain @click="deleteSnapshot">删除 Apple Music CSV</el-button>
      </div>
    </section>

    <el-alert
      v-if="snapshot && isStale"
      type="warning"
      :closable="false"
      show-icon
      :title="`Apple Music 快照已导入 ${ageDays} 天，请重新导出并导入 CSV 后再执行补齐。`"
    />

    <section class="media-library-card" v-loading="mediaSourcesLoading">
      <div>
        <span class="section-label">飞牛整理媒体库</span>
        <p>仅用于资料库对账；与操作台的下载/待整理目录相互独立。</p>
      </div>
      <div class="media-library-actions"><el-button type="primary" @click="showMediaBrowser = true">添加媒体库文件夹</el-button></div>
      <div v-if="mediaSources.length" class="media-source-list">
        <div v-for="source in mediaSources" :key="source.id" :class="{ offline: !source.exists }"><span :title="source.path">{{ source.path }}</span><el-tag size="small" :type="source.exists ? 'success' : 'danger'">{{ source.exists ? '可访问' : '不可访问' }}</el-tag><el-button link type="danger" @click="removeMediaSource(source)">移除</el-button></div>
      </div>
      <p v-else class="media-source-empty">尚未添加媒体库。添加整理后的飞牛音乐目录后才能开始对账。</p>
    </section>

    <section class="snapshot-card">
      <div>
        <span class="section-label">当前 Apple Music 快照</span>
        <strong>{{ snapshotDescription }}</strong>
      </div>
      <dl v-if="snapshot">
        <div><dt>目录曲目</dt><dd>{{ snapshot.catalog_count }}</dd></div>
        <div><dt>用户上传</dt><dd>{{ snapshot.uploaded_count }}</dd></div>
        <div><dt>有 ISRC</dt><dd>{{ snapshot.isrc_count }}</dd></div>
      </dl>
    </section>

    <section v-if="incrementalEntries.length" class="incremental-card">
      <div class="incremental-heading"><div><span class="section-label">Apple Music 增量记录</span><p>手动添加和自动交接的曲目会在这里等待下一次 CSV 快照确认。</p></div><strong>{{ incrementalEntries.length }} 首</strong></div>
      <div class="incremental-list"><div v-for="entry in incrementalEntries" :key="entry.id"><div><strong>{{ entry.title }}</strong><span>{{ entry.artist }}<template v-if="entry.album"> · {{ entry.album }}</template></span></div><el-tag size="small" :type="entry.verification_status === 'confirmed' ? 'success' : 'warning'">{{ entry.verification_status === 'confirmed' ? '快照已确认' : '待快照确认' }}</el-tag><span class="incremental-source">{{ entry.source === 'handoff' ? '自动交接' : entry.source === 'catalog' ? 'Apple 曲库添加' : '手工录入' }}</span><el-button link type="danger" @click="deleteIncrementalEntry(entry)">删除</el-button></div></div>
    </section>

    <section v-if="snapshot" class="summary-grid">
      <button v-for="option in statusOptions.slice(1)" :key="option.value" type="button" class="summary-card" :class="[`status-${option.value}`, { active: statusFilter === option.value }]" @click="statusFilter = option.value; applyFilters()">
        <span>{{ option.label }}</span><strong>{{ summary[option.value as ReconciliationStatus] }}</strong>
      </button>
    </section>

    <section v-if="snapshot" class="workspace-card" v-loading="loading">
      <div class="toolbar">
        <el-select v-model="statusFilter" class="status-select" @change="applyFilters">
          <el-option v-for="option in statusOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
        <el-input v-model="search" clearable placeholder="搜索歌名、歌手、专辑、ISRC" @keyup.enter="applyFilters" @clear="applyFilters" />
        <el-button @click="applyFilters">搜索</el-button>
        <template v-if="selectedReviewCount">
          <el-button type="primary" @click="batchSave('confirmed')">批量确认（{{ selectedReviewCount }}）</el-button>
          <el-button type="danger" plain @click="batchSave('rejected')">批量排除（{{ selectedReviewCount }}）</el-button>
        </template>
      </div>

      <el-table :data="entries" row-key="id" class="reconciliation-table" @selection-change="selectedReviews = $event">
        <el-table-column type="selection" width="52" :selectable="selectableReview" />
        <el-table-column label="状态" width="145">
          <template #default="{ row }"><el-tag :type="row.status === 'both' ? 'success' : row.status === 'review' ? 'warning' : 'info'">{{ statusLabels[row.status as ReconciliationStatus] }}</el-tag></template>
        </el-table-column>
        <el-table-column label="Apple Music" min-width="260">
          <template #default="{ row }">
            <div class="track-title">{{ displayTitle(row.apple) }}</div>
            <div class="track-meta">{{ displaySubtitle(row.apple) }}</div>
            <div v-if="row.apple?.isrc" class="track-code">ISRC {{ row.apple.isrc }}</div>
          </template>
        </el-table-column>
        <el-table-column label="飞牛媒体库" min-width="260">
          <template #default="{ row }">
            <div class="track-title">{{ displayTitle(displayLocal(row)) }}</div>
            <div class="track-meta">{{ displaySubtitle(displayLocal(row)) }}</div>
            <div v-if="displayLocal(row)?.isrc" class="track-code">ISRC {{ displayLocal(row)?.isrc }}</div>
            <template v-if="row.status === 'review'">
              <el-select v-model="selectedCandidates[row.id]" placeholder="选择本地媒体库候选" class="candidate-select">
                <el-option v-for="candidate in row.candidates" :key="candidate.id" :value="candidate.id" :label="`${displayTitle(candidate)} · ${displaySubtitle(candidate)}`" />
              </el-select>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="匹配依据" width="190">
          <template #default="{ row }">{{ reasonLabels[row.match_reason] || row.match_reason }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'review'">
              <el-button link type="primary" @click="saveDecision(row, 'confirmed')">确认</el-button>
              <el-button link type="danger" @click="saveDecision(row, 'rejected')">排除</el-button>
            </template>
            <el-button v-else-if="row.status === 'nas_only'" link type="primary" @click="handoffLocal(row)">补到 Apple Music</el-button>
            <RouterLink v-else-if="row.status === 'apple_only'" :to="{ path: '/discovery', query: { q: [row.apple?.title, row.apple?.artist].filter(Boolean).join(' ') } }"><el-button link type="primary">搜索并补到飞牛</el-button></RouterLink>
            <span v-else class="muted-action">—</span>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!entries.length && !loading" description="没有符合条件的对账记录" />
      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="loadReconciliation()"
      />
    </section>

    <el-empty v-else-if="!loading" description="先导入 TuneMyMusic 导出的 Apple Music CSV，才能开始对账">
      <el-button type="primary" @click="chooseCsv">选择 CSV 文件</el-button>
    </el-empty>
    <ServerFileBrowser v-model="showMediaBrowser" mode="directory" @select="addMediaSources" />
    <el-dialog v-model="incrementalOpen" title="添加 Apple Music 曲目信息" width="min(520px, 92vw)">
      <p class="incremental-hint">用于记录你已经在 Apple Music App 中添加的歌曲。记录会先标记为待确认，下次导入 CSV 时自动核对。</p>
      <el-form label-position="top"><el-form-item label="歌名"><el-input v-model="incrementalForm.title" /></el-form-item><el-form-item label="歌手"><el-input v-model="incrementalForm.artist" /></el-form-item><el-form-item label="专辑"><el-input v-model="incrementalForm.album" /></el-form-item><el-form-item label="ISRC（可选）"><el-input v-model="incrementalForm.isrc" /></el-form-item><el-form-item label="Apple ID（可选）"><el-input v-model="incrementalForm.apple_id" /></el-form-item></el-form>
      <template #footer><el-button @click="incrementalOpen = false">取消</el-button><el-button type="primary" :loading="incrementalSaving" @click="addIncrementalEntry">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.reconciliation-page { max-width: 1440px; margin: 0 auto; padding: 28px; }
.page-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 20px; }
.page-heading h1 { margin: 4px 0 8px; font-size: 30px; }
.page-heading p { margin: 0; color: var(--mf-text-muted); }
.eyebrow, .section-label { color: #7558d9 !important; font-size: 12px; font-weight: 700; letter-spacing: .12em; }
.heading-actions { display: flex; gap: 10px; }
.file-input { display: none; }
.snapshot-card, .workspace-card { margin-top: 18px; border: 1px solid var(--mf-border); border-radius: 18px; background: var(--mf-surface); box-shadow: 0 14px 34px rgb(35 24 78 / 6%); }
.media-library-card { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:14px; padding:18px 24px; margin-top:18px; border:1px solid var(--mf-border); border-radius:18px; background:var(--mf-surface); }.media-library-card p { margin:6px 0 0; color:var(--mf-text-muted); font-size:12px; }.media-source-list { grid-column:1 / -1; display:flex; flex-direction:column; gap:7px; }.media-source-list > div { display:flex; align-items:center; gap:8px; padding:8px 10px; border-radius:9px; background:var(--mf-surface-muted, #f6f7fb); }.media-source-list span { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.media-source-list .offline { color:#b35c58; }.media-source-empty { grid-column:1 / -1; padding:10px 0 0; }
.snapshot-card { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 20px 24px; }
.snapshot-card strong { display: block; margin-top: 6px; font-size: 15px; }
.snapshot-card dl { display: flex; gap: 28px; margin: 0; }
.snapshot-card dl div { min-width: 76px; }
.snapshot-card dt { color: var(--mf-text-muted); font-size: 12px; }
.snapshot-card dd { margin: 5px 0 0; font-size: 22px; font-weight: 700; }
.incremental-card { margin-top: 18px; padding: 18px 24px; border: 1px solid var(--mf-border); border-radius: 18px; background: var(--mf-surface); }.incremental-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; }.incremental-heading p { margin:6px 0 0; color:var(--mf-text-muted); font-size:12px; }.incremental-list { display:flex; flex-direction:column; gap:7px; margin-top:14px; }.incremental-list > div { display:grid; grid-template-columns:minmax(220px,1fr) auto 100px auto; gap:12px; align-items:center; padding:10px 12px; border-radius:10px; background:var(--mf-surface-muted, #f6f7fb); }.incremental-list strong,.incremental-list span { display:block; }.incremental-list span { margin-top:3px; color:var(--mf-text-muted); font-size:12px; }.incremental-list .incremental-source { margin:0; }.incremental-hint { margin-top:0; color:var(--mf-text-muted); font-size:13px; line-height:1.7; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: 16px; }
.summary-card { display: flex; align-items: center; justify-content: space-between; padding: 18px 20px; color: var(--mf-text); border: 1px solid var(--mf-border); border-radius: 16px; background: var(--mf-surface); cursor: pointer; text-align: left; }
.summary-card strong { font-size: 26px; }
.summary-card.active { border-color: #8f75e8; box-shadow: 0 0 0 2px rgb(117 88 217 / 12%); }
.workspace-card { padding: 18px; }
.toolbar { display: grid; grid-template-columns: 180px minmax(240px, 1fr) auto; gap: 10px; margin-bottom: 16px; }
.track-title { font-weight: 650; }
.track-meta, .track-code { margin-top: 4px; color: var(--mf-text-muted); font-size: 12px; line-height: 1.45; }
.track-code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.candidate-select { width: 100%; margin-top: 10px; }
.muted-action { color: var(--mf-text-muted); }
.el-pagination { justify-content: flex-end; margin-top: 18px; }
@media (max-width: 900px) {
  .reconciliation-page { padding: 18px 14px 86px; }
  .page-heading, .snapshot-card { align-items: stretch; flex-direction: column; }
  .media-library-card { grid-template-columns:1fr; padding:18px; }.media-library-actions { display:flex; }.media-library-actions :deep(.el-button) { flex:1; }
  .heading-actions { flex-wrap: wrap; }
  .snapshot-card dl { justify-content: space-between; gap: 10px; }
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .toolbar { grid-template-columns: 1fr; }
}
</style>
