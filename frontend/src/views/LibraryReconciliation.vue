<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import ServerFileBrowser from '../components/ServerFileBrowser.vue'
import AppleFillReviewDialog from '../components/AppleFillReviewDialog.vue'
import TablePagination from '../components/TablePagination.vue'
import { useAppStore } from '../stores/app'

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
  name: string
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
  source: 'manual' | 'catalog' | 'handoff' | 'direct_upload'
  verification_status: 'pending' | 'manual_confirmed' | 'confirmed' | 'absent'
  updated_at: string
  manual_confirmed_at: string | null
  linked_track_key: string | null
  snapshot_status: 'matched' | 'unmatched' | 'no_snapshot'
  matched_track: TrackSide | null
  match_reason: string
  metadata_variants: (TrackSide & { manual_confirmed_at?: string })[]
}

interface IncrementalReview {
  entry: AppleIncrementalEntry
  candidates: (TrackSide & { match_reason: string })[]
  total: number
}

const fileInput = ref<HTMLInputElement>()
const router = useRouter()
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
const localOnlyCandidates = ref<TrackSide[]>([])
const localOnlyOptions = computed(() => localOnlyCandidates.value.map(candidate => ({
  value: candidate.id || '',
  label: `${displayTitle(candidate)} · ${displaySubtitle(candidate)}`,
})))
const summary = ref<Record<ReconciliationStatus, number>>({ both: 0, nas_only: 0, apple_only: 0, review: 0 })
const selectedCandidates = reactive<Record<string, string>>({})
const selectedReviews = ref<ReconciliationEntry[]>([])
const selectedReviewCount = computed(() => selectedReviews.value.filter(entry => entry.status === 'review').length)
const mediaSources = ref<MediaLibrarySource[]>([])
const showMediaBrowser = ref(false)
const mediaDialogOpen = ref(false)
const editingMediaId = ref<string | null>(null)
const mediaForm = reactive({ name: '', path: '' })
const mediaSaving = ref(false)
const mediaSourcesLoading = ref(false)
const incrementalEntries = ref<AppleIncrementalEntry[]>([])
const activeTab = ref('reconciliation')
const incrementalSearch = ref('')
const incrementalFilter = ref('')
const incrementalPage = ref(1)
const incrementalPageSize = ref(20)
const filteredIncrementalEntries = computed(() => {
  const query = incrementalSearch.value.trim().toLocaleLowerCase()
  return incrementalEntries.value.filter(entry => {
    const matchesStatus = !incrementalFilter.value
      || (incrementalFilter.value === 'manual_confirmed' ? !!entry.manual_confirmed_at
        : incrementalFilter.value === 'pending' ? !entry.manual_confirmed_at && entry.verification_status !== 'confirmed'
          : entry.snapshot_status === incrementalFilter.value)
    return matchesStatus && (!query || [entry.title, entry.artist, entry.album, entry.isrc, entry.apple_id]
      .some(value => value?.toLocaleLowerCase().includes(query)))
  })
})
const pagedIncrementalEntries = computed(() => filteredIncrementalEntries.value.slice(
  (incrementalPage.value - 1) * incrementalPageSize.value, incrementalPage.value * incrementalPageSize.value,
))
const reconciliationTotal = computed(() => Object.values(summary.value).reduce((sum, count) => sum + count, 0))
watch([incrementalSearch, incrementalFilter], () => { incrementalPage.value = 1 })
watch(() => filteredIncrementalEntries.value.length, length => {
  incrementalPage.value = Math.min(incrementalPage.value, Math.max(1, Math.ceil(length / incrementalPageSize.value)))
})
const reviewOpen = ref(false)
const reviewLoading = ref(false)
const reviewSaving = ref(false)
const reviewData = ref<IncrementalReview | null>(null)
const reviewEntryId = ref('')
const reviewSearch = ref('')
const duplicateRecords = computed(() => {
  const entry = reviewData.value?.entry
  if (!entry) return []
  return incrementalEntries.value.filter(other => other.id !== entry.id
    && other.artist === entry.artist && other.album === entry.album
    && duplicateTitle(other.title) === duplicateTitle(entry.title))
})

function duplicateTitle(title: string) {
  return title.normalize('NFKC').replace(/\s*\([^()]*\)\s*$/, '').toLocaleLowerCase().replace(/\s/g, '')
}
const incrementalOpen = ref(false)
const incrementalSaving = ref(false)
const incrementalForm = reactive({ title: '', artist: '', album: '', isrc: '', apple_id: '' })
const store = useAppStore()
const appleProcessingPlan = ref('')
const applePlans = computed(() => store.watchFolders.filter(plan => plan.targets.some(target => target.type === 'convert' && target.library !== 'nas' && store.profiles.some(profile => profile.id === target.profileId && profile.enabled && profile.appleMusicDeliveryMode !== 'none'))))
const appleReviewOpen = ref(false)
const appleReviewLocal = ref<TrackSide | null>(null)

const snapshotDescription = computed(() => {
  if (!snapshot.value) return '尚未导入 Apple Music 资料库快照'
  return `${snapshot.value.source_filename} · ${snapshot.value.row_count} 首 · ${formatTime(snapshot.value.imported_at)}`
})

const statusOptions: Array<{ value: ReconciliationStatus | '', label: string }> = [
  { value: '', label: '全部' },
  { value: 'both', label: '双库都有' },
  { value: 'nas_only', label: '仅本地有' },
  { value: 'apple_only', label: '仅 Apple Music 有' },
  { value: 'review', label: '待确认' },
]

const statusLabels: Record<ReconciliationStatus, string> = {
  both: '双库都有',
  nas_only: '仅本地有',
  apple_only: '仅 Apple Music 有',
  review: '待确认',
}

const reasonLabels: Record<string, string> = {
  file_metadata: '同一处理任务的文件标签一致',
  apple_id: 'Apple ID 一致',
  manual_link: '人工关联的快照曲目',
  search: '搜索结果，需人工核对',
  isrc: 'ISRC 一致',
  metadata_exact: '歌名、歌手和专辑一致',
  title_artist: '歌名和歌手一致',
  title_artist_album_diff: '歌名和歌手一致（专辑不同）',
  title_artist_similar: '歌名一致，歌手名相似，等待确认',
  title_subject_artist_compatible: '歌名主体一致、歌手一致或相似，等待确认',
  title_credit_compatible: '歌名相似、署名信息相关，等待确认',
  metadata_similar: '歌名与歌手或专辑相似，等待确认',
  title_cover_review: '同名作品，歌手或版本不同，请试听确认',
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
  if (entry.local) return entry.local
  const candidates = entry.status === 'apple_only' ? localOnlyCandidates.value : entry.candidates
  return candidates.find(candidate => candidate.id === selectedCandidates[entry.id]) || null
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

async function loadIncrementalReview() {
  const entryId = reviewEntryId.value
  reviewLoading.value = true
  try {
    const response = await axios.get<IncrementalReview>(`/api/apple-library/entries/${entryId}/review`, {
      params: { search: reviewSearch.value.trim() },
    })
    if (entryId === reviewEntryId.value) reviewData.value = response.data
  } catch (error) {
    if (entryId !== reviewEntryId.value) return
    reviewData.value = null
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '读取核对详情失败' : '读取核对详情失败')
  } finally {
    if (entryId === reviewEntryId.value) reviewLoading.value = false
  }
}

function openIncrementalReview(entry: AppleIncrementalEntry) {
  reviewEntryId.value = entry.id
  reviewSearch.value = ''
  reviewData.value = null
  reviewOpen.value = true
  loadIncrementalReview()
}

async function mergeDuplicateRecord(source: AppleIncrementalEntry) {
  if (!reviewData.value) return
  const target = reviewData.value.entry
  try {
    await ElMessageBox.confirm(`确认“${source.title}”与“${target.title}”是同一版本吗？合并后保留“${target.title}”这条记录，原名称、确认依据和配对关系会留档，不会删除音乐或重新上传。`,
      '合并重复添加记录', { confirmButtonText: '确认同一版本并合并', cancelButtonText: '取消', type: 'warning' })
    reviewSaving.value = true
    await axios.post(`/api/apple-library/entries/${target.id}/merge`, { source_id: source.id })
    await loadIncrementalEntries()
    await loadIncrementalReview()
    await loadReconciliation()
    ElMessage.success('重复记录已合并，原名称与确认依据已保留')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '合并失败' : '合并失败')
  } finally {
    reviewSaving.value = false
  }
}

async function linkSnapshotCandidate(candidate: TrackSide | null) {
  if (!reviewData.value) return
  const entry = reviewData.value.entry
  try {
    await ElMessageBox.confirm(candidate
      ? `确认“${entry.title} · ${entry.artist}”与快照中的“${candidate.title} · ${candidate.artist} · ${candidate.album || '无专辑'}”是同一版本吗？`
      : '撤销与快照曲目的人工关联吗？原有人工确认记录仍会保留。',
    candidate ? '关联快照曲目' : '撤销关联', { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' })
    reviewSaving.value = true
    await axios.put(`/api/apple-library/entries/${entry.id}/snapshot-link`, { track_key: candidate?.track_key || null })
    await loadIncrementalEntries()
    await loadIncrementalReview()
    await loadReconciliation()
    ElMessage.success(candidate ? '已保存关联，后续快照将继续核对' : '已撤销人工关联')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '保存关联失败' : '保存关联失败')
  } finally {
    reviewSaving.value = false
  }
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
    await loadReconciliation()
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
    await loadReconciliation()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '删除记录失败' : '删除记录失败')
  }
}

async function confirmIncrementalEntry(entry: AppleIncrementalEntry) {
  try {
    await ElMessageBox.confirm(`确认“${entry.title} · ${entry.artist}”已在 Apple Music 资料库中吗？`, '手动确认', {
      confirmButtonText: '确认已添加', cancelButtonText: '取消', type: 'warning',
    })
    await axios.post(`/api/apple-library/entries/${entry.id}/confirm`)
    await loadIncrementalEntries()
    await loadReconciliation()
    ElMessage.success('已手动确认；后续导入 CSV 仍可自动核对')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '确认失败' : '确认失败')
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

function openMediaDialog(source?: MediaLibrarySource) {
  editingMediaId.value = source?.id || null
  Object.assign(mediaForm, { name: source?.name || '', path: source?.path || '' })
  mediaDialogOpen.value = true
}

function selectMediaPath(paths: string[]) {
  mediaForm.path = paths[0] || ''
  if (!mediaForm.name) mediaForm.name = mediaForm.path.split(/[\\/]/).filter(Boolean).pop() || ''
}

async function saveMediaSource() {
  if (!mediaForm.name.trim() || !mediaForm.path.trim()) return ElMessage.warning('请填写目录名称和目录地址')
  mediaSaving.value = true
  try {
    const payload = { name: mediaForm.name.trim(), path: mediaForm.path.trim() }
    if (editingMediaId.value) await axios.put(`/api/library/media-sources/${editingMediaId.value}`, payload)
    else await axios.post('/api/library/media-sources', payload)
    mediaDialogOpen.value = false
    await loadMediaSources()
    ElMessage.success('本地音乐库目录已保存')
    if (snapshot.value) await loadReconciliation(true)
  } catch (error) {
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '保存媒体库失败' : '保存媒体库失败')
  } finally {
    mediaSaving.value = false
  }
}

async function removeMediaSource(source: MediaLibrarySource) {
  try {
    await ElMessageBox.confirm(`停止用于对账读取“${source.name}”吗？不会删除其中的媒体文件。`, '移除媒体库', {
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

async function loadLocalOnlyCandidates() {
  const candidates: TrackSide[] = []
  for (let offset = 0; ; offset += 1000) {
    const response = await axios.get<ReconciliationResponse>('/api/library/reconciliation', {
      params: { status: 'nas_only', offset, limit: 1000 },
    })
    candidates.push(...response.data.entries.flatMap(entry => entry.local ? [entry.local] : []))
    if (candidates.length >= response.data.total) break
  }
  localOnlyCandidates.value = candidates
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
    if (entries.value.some(entry => entry.status === 'apple_only')) {
      await loadLocalOnlyCandidates()
    }
    for (const entry of entries.value) {
      if (entry.status === 'review' && entry.candidates.length) {
        selectedCandidates[entry.id] = entry.candidates[0].id || ''
      } else if (entry.status === 'apple_only' &&
        !localOnlyCandidates.value.some(candidate => candidate.id === selectedCandidates[entry.id])) {
        delete selectedCandidates[entry.id]
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
    const response = snapshot.value
      ? await axios.put(`/api/apple-library/snapshots/${snapshot.value.id}`, form)
      : await axios.post('/api/apple-library/snapshots', form)
    ElMessage.success(response.data.created ? 'Apple Music 快照已保存' : '快照内容未变化')
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
  try {
    await axios.post('/api/library/matches', {
      local_file_id: localFileId,
      apple_track_key: appleTrackKey,
      decision,
      require_only_unmatched: entry.status === 'apple_only',
    })
    delete selectedCandidates[entry.id]
    ElMessage.success(decision === 'confirmed' ? '匹配已确认' : '候选已排除')
    await loadReconciliation()
  } catch (error) {
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '保存匹配失败' : '保存匹配失败')
    if (axios.isAxiosError(error) && error.response?.status === 409) await loadReconciliation()
  }
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
      `确定删除“${snapshot.value.source_filename}”及其导入数据吗？不会删除本地音乐文件。`,
      '删除 Apple Music CSV 快照',
      { confirmButtonText: '删除快照', cancelButtonText: '取消', type: 'warning' },
    )
    await axios.delete(`/api/apple-library/snapshots/${snapshot.value.id}`)
    await loadStatus()
    await loadIncrementalEntries()
    entries.value = []
    total.value = 0
    summary.value = { both: 0, nas_only: 0, apple_only: 0, review: 0 }
    if (snapshot.value && mediaSources.value.length) await loadReconciliation()
    ElMessage.success('Apple Music CSV 快照已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '删除快照失败' : '删除快照失败')
  }
}

function handoffLocal(entry: ReconciliationEntry) {
  if (!entry.local?.id) return
  if (!applePlans.value.some(plan => plan.id === appleProcessingPlan.value)) appleProcessingPlan.value = applePlans.value[0]?.id || ''
  appleReviewLocal.value = entry.local
  appleReviewOpen.value = true
}

async function fillLocalApple() {
  if (!appleReviewLocal.value?.id || !appleProcessingPlan.value) return
  try {
    const response = await axios.post('/api/discovery/fill-local-apple', {
      local_file_id: appleReviewLocal.value.id,
      processing_plan_id: appleProcessingPlan.value,
    })
    const errors = response.data.outputs.filter((item: { state: string }) => ['failed', 'blocked'].includes(item.state))
    if (errors.length) ElMessage.warning(errors[0].error || '部分输出失败，请查看操作记录')
    else ElMessage.success(response.data.created_tasks ? '已使用本地文件创建转换任务，上传进度请查看操作记录' : '已有输出或处理记录，请在操作记录中核对')
    await loadIncrementalEntries()
    await loadReconciliation()
  } catch (error) {
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '本地补齐失败' : '本地补齐失败')
  }
}

function searchAppleFill() {
  const title = appleReviewLocal.value?.title || (appleReviewLocal.value?.filename || '').replace(/\.[^.]+$/, '')
  appleReviewOpen.value = false
  router.push({ path: '/discovery', query: { q: title } })
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([store.fetchProfiles(), store.fetchWatchFolders()])
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
        <p>将多个本地目录作为一个音乐库，与 Apple Music 资料库对账。</p>
      </div>
    </section>

    <el-alert
      v-if="snapshot && isStale"
      type="warning"
      :closable="false"
      show-icon
      :title="`Apple Music 快照已导入 ${ageDays} 天，请重新导出并导入 CSV 后再执行补齐。`"
    />

    <div class="library-setup">
    <section class="media-library-card" v-loading="mediaSourcesLoading">
      <div class="card-heading"><div><span class="section-label">本地音乐库</span><p>多个目录合并对账；与操作台的下载/待整理目录相互独立。</p></div><div class="card-actions"><el-button @click="openMediaDialog()">添加目录</el-button><el-button :disabled="!snapshot || !mediaSources.length" :loading="loading" @click="loadReconciliation(true)">重新扫描</el-button></div></div>
      <div v-if="mediaSources.length" class="media-source-list">
        <div v-for="source in mediaSources" :key="source.id" :class="{ offline: !source.exists }"><div class="source-details"><strong>{{ source.name }}</strong><span :title="source.path">{{ source.path }}</span></div><el-tag size="small" :type="source.exists ? 'success' : 'danger'">{{ source.exists ? '可访问' : '不可访问' }}</el-tag><el-button link @click="openMediaDialog(source)">修改</el-button><el-button link type="danger" @click="removeMediaSource(source)">移除</el-button></div>
      </div>
      <p v-else class="media-source-empty">尚未添加目录。添加整理后的本地音乐目录后即可对账。</p>
    </section>

    <section class="snapshot-card">
      <div class="card-heading"><div><span class="section-label">Apple Music 快照</span><strong>{{ snapshotDescription }}</strong></div><div class="card-actions"><input ref="fileInput" class="file-input" type="file" accept=".csv,text/csv" @change="uploadCsv" /><el-button :loading="uploading" @click="chooseCsv">{{ snapshot ? '更新快照' : '导入快照' }}</el-button><el-button v-if="snapshot" type="danger" plain @click="deleteSnapshot">删除快照</el-button></div></div>
      <dl v-if="snapshot">
        <div><dt>目录曲目</dt><dd>{{ snapshot.catalog_count }}</dd></div>
        <div><dt>用户上传</dt><dd>{{ snapshot.uploaded_count }}</dd></div>
        <div><dt>有 ISRC</dt><dd>{{ snapshot.isrc_count }}</dd></div>
      </dl>
    </section>
    </div>

    <el-tabs v-model="activeTab" class="library-tabs">
    <el-tab-pane label="音乐库对账" name="reconciliation">

    <section v-if="snapshot" class="summary-grid">
      <button v-for="option in statusOptions" :key="option.value" type="button" class="summary-card" :class="[`status-${option.value}`, { active: statusFilter === option.value }]" :aria-pressed="statusFilter === option.value" @click="statusFilter = option.value; applyFilters()">
        <span>{{ option.label }}</span><strong>{{ option.value ? summary[option.value] : reconciliationTotal }}</strong>
      </button>
    </section>

    <section v-if="snapshot" class="workspace-card" v-loading="loading">
      <div class="toolbar">
        <el-select v-model="statusFilter" popper-class="library-select-dropdown" class="status-select" placeholder="全部" @change="applyFilters">
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
        <el-table-column label="本地音乐库" min-width="260">
          <template #default="{ row }">
            <div class="track-title">{{ displayTitle(displayLocal(row)) }}</div>
            <div class="track-meta">{{ displaySubtitle(displayLocal(row)) }}</div>
            <div v-if="displayLocal(row)?.isrc" class="track-code">ISRC {{ displayLocal(row)?.isrc }}</div>
            <template v-if="row.status === 'review'">
              <el-select v-model="selectedCandidates[row.id]" popper-class="library-select-dropdown" filterable placeholder="选择本地音乐库候选" class="candidate-select">
                <el-option v-for="candidate in row.candidates" :key="candidate.id" :value="candidate.id" :label="`${displayTitle(candidate)} · ${displaySubtitle(candidate)}`" />
              </el-select>
            </template>
            <el-select-v2 v-else-if="row.status === 'apple_only'" v-model="selectedCandidates[row.id]" popper-class="library-select-dropdown" :options="localOnlyOptions" filterable clearable placeholder="搜索仅本地有的歌曲" class="candidate-select" />
          </template>
        </el-table-column>
        <el-table-column label="匹配依据" width="190">
          <template #default="{ row }">{{ reasonLabels[row.match_reason] || row.match_reason }}</template>
        </el-table-column>
        <el-table-column label="操作" width="225" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'review'">
              <el-button link type="primary" @click="saveDecision(row, 'confirmed')">确认</el-button>
              <el-button link type="danger" @click="saveDecision(row, 'rejected')">排除</el-button>
            </template>
            <el-button v-else-if="row.status === 'nas_only'" link type="primary" @click="handoffLocal(row)">补到 Apple Music</el-button>
            <template v-else-if="row.status === 'apple_only'">
              <el-button link type="primary" @click="saveDecision(row, 'confirmed')">确认</el-button>
              <RouterLink :to="{ path: '/discovery', query: { q: [row.apple?.title, row.apple?.artist].filter(Boolean).join(' ') } }"><el-button link type="primary">搜索并补到本地</el-button></RouterLink>
            </template>
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
    </el-tab-pane>
    <el-tab-pane :label="`添加记录（${incrementalEntries.length}）`" name="incremental">
      <section class="workspace-card">
        <div class="incremental-heading"><div><span class="section-label">Apple Music 添加记录</span><p>人工确认持续保留；快照未匹配只表示存在差异，不代表歌曲已删除。</p></div><el-button @click="incrementalOpen = true">添加记录</el-button></div>
        <div class="toolbar incremental-toolbar">
          <el-select v-model="incrementalFilter" popper-class="library-select-dropdown" aria-label="筛选添加记录" placeholder="全部记录">
            <el-option label="全部记录" value="" />
            <el-option label="待确认" value="pending" />
            <el-option label="人工已确认" value="manual_confirmed" />
            <el-option label="快照已匹配" value="matched" />
            <el-option label="快照未匹配" value="unmatched" />
          </el-select>
          <el-input v-model="incrementalSearch" clearable aria-label="搜索添加记录" placeholder="搜索歌名、歌手、专辑、ISRC 或 Apple ID" />
          <span class="track-meta">{{ filteredIncrementalEntries.length }} 条记录</span>
        </div>
        <el-table :data="pagedIncrementalEntries" row-key="id" class="incremental-table" empty-text="没有符合条件的添加记录">
          <el-table-column label="歌曲信息" min-width="260"><template #default="{ row }"><div class="track-title">{{ row.title }}</div><div class="track-meta">{{ row.artist }}<template v-if="row.album"> · {{ row.album }}</template></div></template></el-table-column>
          <el-table-column label="人工确认" width="155"><template #default="{ row }"><el-tag :type="row.manual_confirmed_at ? 'success' : 'info'">{{ row.manual_confirmed_at ? '人工已确认' : '尚未人工确认' }}</el-tag><div v-if="row.manual_confirmed_at" class="track-meta">{{ formatTime(row.manual_confirmed_at) }}</div></template></el-table-column>
          <el-table-column label="快照核对" min-width="190"><template #default="{ row }"><el-tag :type="row.snapshot_status === 'matched' ? 'success' : row.snapshot_status === 'unmatched' ? 'warning' : 'info'">{{ row.snapshot_status === 'matched' ? '快照已匹配' : row.snapshot_status === 'unmatched' ? '当前快照未匹配' : '尚未导入快照' }}</el-tag><div v-if="row.snapshot_status === 'matched'" class="track-meta">{{ reasonLabels[row.match_reason] || row.match_reason }}</div></template></el-table-column>
          <el-table-column label="来源" width="130"><template #default="{ row }">{{ row.source === 'direct_upload' ? '独立上传提交' : row.source === 'handoff' ? '自动交接' : row.source === 'catalog' ? 'Apple 曲库添加' : '手工录入' }}</template></el-table-column>
          <el-table-column label="操作" width="230" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openIncrementalReview(row)">核对详情</el-button><el-button v-if="!row.manual_confirmed_at" link type="primary" @click="confirmIncrementalEntry(row)">人工确认</el-button><el-button link type="danger" @click="deleteIncrementalEntry(row)">删除</el-button></template></el-table-column>
        </el-table>
        <TablePagination v-model:current-page="incrementalPage" v-model:page-size="incrementalPageSize" popper-class="library-select-dropdown" :total="filteredIncrementalEntries.length" />
      </section>
    </el-tab-pane>
    </el-tabs>
    <el-dialog v-model="reviewOpen" title="核对 Apple Music 添加记录" width="min(960px, 94vw)" :close-on-click-modal="false" :close-on-press-escape="!reviewSaving" :show-close="!reviewSaving">
      <div v-loading="reviewLoading">
        <template v-if="reviewData">
          <p class="incremental-hint">原记录来自文件音乐标签或当时选择的曲目信息。下方比较的是当前 CSV 快照，不是 Apple Music 实时查询；关联前请核对歌手和版本。</p>
          <section v-if="reviewData.entry.metadata_variants?.length" class="record-history">
            <strong>文件标签与合并记录留档</strong>
            <p v-for="(item, index) in reviewData.entry.metadata_variants" :key="index">{{ item.title }} · {{ item.artist }} · {{ item.album || '无专辑' }}<template v-if="item.manual_confirmed_at"> · 人工确认于 {{ formatTime(item.manual_confirmed_at) }}</template></p>
          </section>
          <section v-if="duplicateRecords.length" class="record-history">
            <strong>可能重复的添加记录</strong><p>名称近似不代表同一版本。请确认后合并到当前记录；原记录会留档，不影响音乐文件和上传任务。</p>
            <div v-for="item in duplicateRecords" :key="item.id" class="duplicate-record"><span>{{ item.title }} · {{ item.artist }} · {{ item.album }}（{{ item.snapshot_status === 'matched' ? '快照已匹配' : '快照未匹配' }}）</span><el-button type="primary" link :disabled="reviewLoading || reviewSaving" @click="mergeDuplicateRecord(item)">合并到当前记录</el-button></div>
          </section>
          <div class="evidence-grid">
            <section><strong>原记录</strong><h3>{{ reviewData.entry.title }}</h3><p>歌手：{{ reviewData.entry.artist }}</p><p>专辑：{{ reviewData.entry.album || '—' }}</p><p>ISRC：{{ reviewData.entry.isrc || '—' }}</p><p>Apple ID：{{ reviewData.entry.apple_id || '—' }}</p><p>人工确认：{{ reviewData.entry.manual_confirmed_at ? formatTime(reviewData.entry.manual_confirmed_at) : '尚未确认' }}</p></section>
            <section><strong>当前快照匹配结果</strong><template v-if="reviewData.entry.matched_track"><h3>{{ reviewData.entry.matched_track.title }}</h3><p>歌手：{{ reviewData.entry.matched_track.artist }}</p><p>专辑：{{ reviewData.entry.matched_track.album || '—' }}</p><p>ISRC：{{ reviewData.entry.matched_track.isrc || '—' }}</p><p>Apple ID：{{ reviewData.entry.matched_track.apple_id || '—' }}</p><p>依据：{{ reasonLabels[reviewData.entry.match_reason] || reviewData.entry.match_reason }}</p></template><p v-else>{{ snapshot ? '当前快照未匹配，可搜索并关联曲目。人工确认记录仍保留。' : '尚未导入快照。' }}</p><el-button v-if="reviewData.entry.linked_track_key" link type="danger" :disabled="reviewLoading || reviewSaving" @click="linkSnapshotCandidate(null)">撤销人工关联</el-button></section>
          </div>
          <div class="review-search"><el-input v-model="reviewSearch" clearable :disabled="reviewLoading || reviewSaving || !snapshot" placeholder="搜索当前快照的歌名、歌手、专辑、ISRC 或 Apple ID" aria-label="搜索快照曲目" @keyup.enter="loadIncrementalReview" @clear="loadIncrementalReview" /><el-button :disabled="reviewLoading || reviewSaving || !snapshot" @click="loadIncrementalReview">搜索</el-button></div>
          <p class="track-meta">{{ reviewSearch.trim() ? '搜索结果' : '推荐候选（近似名称不会自动确认）' }} · {{ reviewData.total }} 条<template v-if="reviewData.total > 50">，仅显示前 50 条，请缩小搜索范围</template></p>
          <el-table :data="reviewData.candidates" row-key="track_key" empty-text="未找到候选，可尝试搜索歌名或歌手">
            <el-table-column label="快照曲目" min-width="250"><template #default="{ row }"><div class="track-title">{{ row.title }}</div><div class="track-meta">{{ row.artist }} · {{ row.album || '无专辑' }}</div><div class="track-code">Apple ID {{ row.apple_id || '—' }} · ISRC {{ row.isrc || '—' }}</div></template></el-table-column>
            <el-table-column label="候选依据" min-width="170"><template #default="{ row }">{{ reasonLabels[row.match_reason] || row.match_reason }}</template></el-table-column>
            <el-table-column label="操作" width="100"><template #default="{ row }"><el-button link type="primary" :disabled="reviewLoading || reviewSaving || row.track_key === reviewData.entry.matched_track?.track_key" @click="linkSnapshotCandidate(row)">{{ row.track_key === reviewData.entry.matched_track?.track_key ? '已匹配' : '关联此曲' }}</el-button></template></el-table-column>
          </el-table>
        </template>
      </div>
    </el-dialog>
    <ServerFileBrowser v-model="showMediaBrowser" mode="directory" @select="selectMediaPath" />
    <AppleFillReviewDialog v-model="appleReviewOpen" :payload="appleReviewLocal?.id ? { local_file_id: appleReviewLocal.id } : null" mode="local" :confirm-disabled="!applePlans.some(plan => plan.id === appleProcessingPlan)" @confirm="fillLocalApple" @search="searchAppleFill" @added="loadIncrementalEntries">
      <template #processing-plan><el-form label-position="top"><el-form-item label="Apple Music 转换方案"><el-select v-model="appleProcessingPlan" popper-class="library-select-dropdown" placeholder="选择含上传或交接规则的方案"><el-option v-for="plan in applePlans" :key="plan.id" :label="plan.name" :value="plan.id" /></el-select></el-form-item><p>只使用当前本地歌曲和方案中的 Apple Music 输出，不重新下载，也不执行本地复制规则。</p><RouterLink v-if="!applePlans.length" to="/processing-plans">先配置 Apple Music 转换方案</RouterLink></el-form></template>
    </AppleFillReviewDialog>
    <el-dialog v-model="mediaDialogOpen" :title="editingMediaId ? '修改本地音乐库目录' : '添加本地音乐库目录'" width="min(520px, 92vw)">
      <el-form label-position="top"><el-form-item label="目录名称"><el-input v-model="mediaForm.name" placeholder="例如 华语收藏" /></el-form-item><el-form-item label="目录地址"><el-input v-model="mediaForm.path" placeholder="服务器上的绝对路径" /></el-form-item><el-button @click="showMediaBrowser = true">浏览服务器目录</el-button></el-form>
      <template #footer><el-button @click="mediaDialogOpen = false">取消</el-button><el-button type="primary" :loading="mediaSaving" @click="saveMediaSource">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="incrementalOpen" title="添加 Apple Music 曲目信息" width="min(520px, 92vw)">
      <p class="incremental-hint">用于记录你已经在 Apple Music App 中添加的歌曲。记录会先标记为待确认，下次导入 CSV 时自动核对。</p>
      <el-form label-position="top"><el-form-item label="歌名"><el-input v-model="incrementalForm.title" /></el-form-item><el-form-item label="歌手"><el-input v-model="incrementalForm.artist" /></el-form-item><el-form-item label="专辑"><el-input v-model="incrementalForm.album" /></el-form-item><el-form-item label="ISRC（可选）"><el-input v-model="incrementalForm.isrc" /></el-form-item><el-form-item label="Apple ID（可选）"><el-input v-model="incrementalForm.apple_id" /></el-form-item></el-form>
      <template #footer><el-button @click="incrementalOpen = false">取消</el-button><el-button type="primary" :loading="incrementalSaving" @click="addIncrementalEntry">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.reconciliation-page, :global(.library-select-dropdown) {
  --el-color-primary: #a783fa;
  --el-color-primary-light-3: #bda1fb;
  --el-color-primary-light-5: #d3c0fc;
  --el-color-primary-light-9: var(--mf-nav-hover);
  --el-color-primary-dark-2: #8d66df;
  --el-bg-color: var(--mf-surface);
  --el-bg-color-overlay: var(--mf-surface);
  --el-fill-color-blank: var(--mf-surface);
  --el-fill-color-light: var(--mf-surface-muted);
  --el-border-color: var(--mf-border);
  --el-border-color-light: var(--mf-border);
  --el-border-color-lighter: var(--mf-border);
  --el-text-color-primary: var(--mf-text);
  --el-text-color-regular: var(--mf-text);
  --el-text-color-secondary: var(--mf-text-muted);
  --el-border-radius-base: 11px;
}
.reconciliation-page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 28px;
}
.reconciliation-page :deep(.el-button:not(.is-link):not(.is-text)) { min-height:36px; }
.reconciliation-page :deep(.el-table) { --el-table-bg-color:transparent; --el-table-tr-bg-color:transparent; --el-table-header-bg-color:var(--mf-surface-muted); --el-table-row-hover-bg-color:var(--mf-nav-hover); }
.page-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 20px; }
.page-heading h1 { margin: 4px 0 8px; font-size: 30px; }
.page-heading p { margin: 0; color: var(--mf-text-muted); }
.library-setup { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; align-items:stretch; }
.card-heading { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; }
.card-actions { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
.card-actions :deep(.el-button) { margin:0; }
.eyebrow, .section-label { color: #7558d9 !important; font-size: 12px; font-weight: 700; letter-spacing: .12em; }
.heading-actions { display: flex; gap: 10px; }
.file-input { display: none; }
.snapshot-card, .workspace-card { margin-top: 18px; border: 1px solid var(--mf-border); border-radius: 18px; background: var(--mf-surface); box-shadow: 0 14px 34px rgb(35 24 78 / 6%); }
.media-library-card { padding:20px 24px; border:1px solid var(--mf-border); border-radius:18px; background:var(--mf-surface); box-shadow:0 14px 34px rgb(35 24 78 / 6%); }.media-library-card p { margin:6px 0 0; color:var(--mf-text-muted); font-size:12px; }.media-source-list { display:flex; flex-direction:column; gap:7px; margin-top:18px; }.media-source-list > div { display:flex; align-items:center; gap:8px; padding:8px 10px; border-radius:9px; background:var(--mf-surface-muted, #f6f7fb); }.source-details { flex:1; min-width:0; }.source-details strong,.source-details span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.source-details span { margin-top:3px; color:var(--mf-text-muted); font-size:12px; }.media-source-list .offline { color:#b35c58; }.media-source-empty { padding:10px 0 0; }
.snapshot-card { display:flex; flex-direction:column; justify-content:space-between; gap:24px; padding:20px 24px; margin-top:0; }
.snapshot-card strong { display: block; margin-top: 6px; font-size: 15px; }
.snapshot-card dl { display: flex; gap: 28px; margin: 0; }
.snapshot-card dl div { min-width: 76px; }
.snapshot-card dt { color: var(--mf-text-muted); font-size: 12px; }
.snapshot-card dd { margin: 5px 0 0; font-size: 22px; font-weight: 700; }
.incremental-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; }.incremental-heading p { margin:6px 0 0; color:var(--mf-text-muted); font-size:12px; }.incremental-hint { margin-top:0; color:var(--mf-text-muted); font-size:13px; line-height:1.7; }
.library-tabs { margin-top:24px; }
.library-tabs :deep(.el-tabs__header) { margin:0 0 24px; }
.library-tabs :deep(.el-tabs__nav-wrap::after), .library-tabs :deep(.el-tabs__active-bar) { display:none; }
.library-tabs :deep(.el-tabs__nav) { gap:6px; padding:6px; border:1px solid var(--mf-border); border-radius:17px; background:var(--mf-surface); }
.library-tabs :deep(.el-tabs__item) { height:44px; padding:0 18px !important; border-radius:11px; color:var(--mf-text-muted); transition:background .2s,color .2s; }
.library-tabs :deep(.el-tabs__item:hover) { color:#9873e9; background:var(--mf-nav-hover); }
.library-tabs :deep(.el-tabs__item.is-active) { color:#fff; background:#a783fa; box-shadow:0 4px 12px rgb(151 112 239 / 22%); }
.library-tabs :deep(.el-tabs__item:focus-visible) { outline:2px solid #9873e9; outline-offset:2px; box-shadow:none; }
.incremental-toolbar { margin-top:18px; }
.incremental-table { min-width:900px; }
.evidence-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
.evidence-grid section { min-width:0; padding:16px; border:1px solid var(--mf-border); border-radius:12px; overflow-wrap:anywhere; }
.evidence-grid h3 { margin:12px 0; }
.record-history { margin-bottom:16px; padding:14px 16px; border:1px solid var(--mf-border); border-radius:12px; background:var(--mf-surface-muted); }
.record-history p { color:var(--mf-text-muted); line-height:1.6; }
.duplicate-record { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; }
.evidence-grid p { margin:8px 0; }
.review-search { display:flex; gap:10px; margin-top:20px; }
.summary-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px; margin-top: 16px; }
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
  .library-setup { grid-template-columns:1fr; }
  .evidence-grid { grid-template-columns:1fr; }
  .media-library-card, .snapshot-card { padding:18px; }
  .heading-actions { flex-wrap: wrap; }
  .snapshot-card dl { justify-content: space-between; gap: 10px; }
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .toolbar { grid-template-columns: 1fr; }
  .workspace-card { overflow-x:auto; }
  .reconciliation-table { min-width:900px; }
}
@media (max-width: 560px) {
  .library-tabs :deep(.el-tabs__nav) { width:100%; gap:4px; padding:5px; border-radius:14px; }
  .library-tabs :deep(.el-tabs__item) { flex:1; height:42px; padding:0 8px !important; }
  .card-heading,.incremental-heading { flex-direction:column; align-items:stretch; }
  .card-actions { width:100%; }
  .card-actions :deep(.el-button) { flex:1; }
  .media-source-list > div { flex-wrap:wrap; }
  .source-details { flex-basis:100%; }
  .summary-grid { gap:8px; }
  .summary-card { padding:12px; }
  .summary-card strong { font-size:20px; }
  .snapshot-card dl { flex-wrap:wrap; }
}
</style>
