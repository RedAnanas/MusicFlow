<script setup lang="ts">
import { ref, watch } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'

interface CatalogTrack {
  apple_id: string
  title: string
  artist: string
  album: string
  duration_ms: number
  artwork_url: string
  track_url: string
  country: string
}

interface PersonalTrack {
  title: string
  artist: string
  album?: string
  verification_status?: string
}

interface PrecheckResult {
  personal: PersonalTrack[]
  catalog: CatalogTrack[]
  catalog_error: string
  country: string
}

const props = defineProps<{
  modelValue: boolean
  payload: { local_file_id?: string; selected_track?: object } | null
  mode: 'search' | 'confirm'
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  search: []
  confirm: []
  added: [track: CatalogTrack]
}>()

const loading = ref(false)
const savingId = ref('')
const recordedIds = ref<string[]>([])
const result = ref<PrecheckResult>({ personal: [], catalog: [], catalog_error: '', country: 'cn' })

const candidateKey = (track: CatalogTrack) => track.apple_id || track.track_url || `${track.title}:${track.artist}`

async function loadReview() {
  if (!props.payload) return
  loading.value = true
  recordedIds.value = []
  result.value = { personal: [], catalog: [], catalog_error: '', country: 'cn' }
  try {
    result.value = (await axios.post<PrecheckResult>('/api/discovery/apple-precheck', props.payload)).data
  } catch (error) {
    result.value.catalog_error = axios.isAxiosError(error) ? error.response?.data?.detail || '核对失败' : '核对失败'
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, open => { if (open) loadReview() })

async function markAdded(track: CatalogTrack) {
  const key = candidateKey(track)
  savingId.value = key
  try {
    await axios.post('/api/apple-library/entries', { ...track, source: 'catalog' })
    recordedIds.value.push(key)
    emit('added', track)
    ElMessage.success('已记录为 Apple Music 待确认，导入新快照后会自动核对')
  } catch (error) {
    ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '记录失败' : '记录失败')
  } finally {
    savingId.value = ''
  }
}

function proceed() {
  emit('update:modelValue', false)
  if (props.mode === 'search') emit('search')
  else emit('confirm')
}
</script>

<template>
  <el-dialog :model-value="modelValue" class="apple-fill-review" width="min(920px, 94vw)" append-to-body @update:model-value="emit('update:modelValue', $event)">
    <template #header>
      <div class="review-heading"><div><strong>Apple Music 曲库候选</strong><span>这里仅表示 Apple 曲库可搜索到；在 Apple Music 中添加后再点“已添加”。</span></div><small>{{ result.country.toUpperCase() }}</small></div>
    </template>
    <div v-loading="loading" class="review-content">
      <section v-if="result.personal.length" class="review-section">
        <h3>个人资料库疑似已有</h3>
        <p>这些记录已在快照或增量记录中；请核对是否为同一首作品。</p>
        <div v-for="(track, index) in result.personal" :key="index" class="personal-item"><strong>{{ track.title }}</strong><span>{{ track.artist }} · {{ track.album || '未知专辑' }}{{ track.verification_status === 'pending' ? ' · 待确认' : '' }}</span></div>
      </section>
      <section v-if="result.catalog.length" class="review-section">
        <div class="catalog-cards">
          <article v-for="(track, index) in result.catalog" :key="`${track.apple_id}-${index}`" class="catalog-card">
            <img v-if="track.artwork_url" :src="track.artwork_url" alt="">
            <div v-else class="artwork-placeholder">♫</div>
            <div class="catalog-meta"><strong :title="track.title">{{ track.title }}</strong><span :title="`${track.artist} · ${track.album || '未知专辑'}`">{{ track.artist }} · {{ track.album || '未知专辑' }}</span></div>
            <div class="catalog-buttons"><a :href="track.track_url" target="_blank" rel="noopener noreferrer">在 Apple Music 中打开</a><button type="button" :disabled="recordedIds.includes(candidateKey(track)) || savingId === candidateKey(track)" @click="markAdded(track)">{{ recordedIds.includes(candidateKey(track)) ? '已记录' : '已添加' }}</button></div>
          </article>
        </div>
      </section>
      <p v-if="!loading && !result.personal.length && !result.catalog.length && !result.catalog_error" class="review-empty">未找到疑似已有曲目。可到发现页继续搜索，选择你认可的版本。</p>
      <p v-if="result.catalog_error" class="review-error">{{ result.catalog_error }}。请重试曲库核对，或到发现页手动搜索。</p>
      <el-button v-if="result.catalog_error" @click="loadReview">重试核对</el-button>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="loading || (mode === 'confirm' && (!!result.catalog_error || recordedIds.length > 0))" @click="proceed">{{ mode === 'search' ? '去发现页搜索' : recordedIds.length ? '已记录，等待确认' : '确认补齐所选版本' }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
:global(.apple-fill-review .el-dialog__body){padding-top:4px}
.review-heading{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.review-heading strong,.review-heading span{display:block}.review-heading strong{color:#eee8f3;font-size:20px}.review-heading span{margin-top:5px;color:#a79aae;font-size:13px}.review-heading small{padding:5px 9px;border-radius:8px;background:#30283a;color:#d7c8e7}
.review-content{max-height:min(550px,60vh);min-height:100px;overflow-y:auto}.review-section{margin-bottom:16px}.review-section:last-child{margin-bottom:0}.review-section h3{margin:8px 0;color:#eee8f3;font-size:15px}.review-section p{margin:0 0 10px;color:#a79aae;font-size:12px}.personal-item{display:flex;flex-direction:column;gap:4px;margin-bottom:8px;padding:10px 14px;border:1px solid #443852;border-radius:10px;background:#292231}.personal-item strong{color:#eee8f3}.personal-item span{color:#a79aae;font-size:12px}
.catalog-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.catalog-card{display:grid;grid-template-columns:44px minmax(0,1fr);grid-template-rows:44px 28px;gap:8px 10px;height:102px;min-width:0;padding:10px;box-sizing:border-box;border:1px solid #3c314a;border-radius:11px;background:#251e2c}.catalog-card img,.artwork-placeholder{grid-column:1;grid-row:1;width:44px;height:44px;border-radius:7px;object-fit:cover}.artwork-placeholder{display:grid;place-items:center;background:#352b40;color:#c9b5dd}.catalog-meta{display:flex;min-width:0;flex-direction:column;justify-content:center;gap:4px}.catalog-meta strong,.catalog-meta span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.catalog-meta strong{color:#f0eaf5;font-size:12px}.catalog-meta span{color:#a79aae;font-size:10px}.catalog-buttons{display:flex;grid-column:1/-1;grid-row:2;justify-content:flex-end;gap:8px}.catalog-buttons a,.catalog-buttons button{display:grid;height:28px;min-width:0;place-items:center;padding:0 10px;border:1px solid #564565;border-radius:6px;background:#2b2235;color:#dcc9e8;font-size:10px;font-weight:600;font-family:inherit;text-decoration:none;white-space:nowrap;cursor:pointer}.catalog-buttons a{width:196px}.catalog-buttons button{width:78px}.catalog-buttons button:disabled{opacity:.65;cursor:default}.review-empty,.review-error{margin:12px 0;color:#afa1bc;font-size:13px;line-height:1.6}.review-error{color:#e8a6a6}
@media(max-width:720px){.review-content{max-height:70vh}.catalog-cards{grid-template-columns:1fr}.catalog-buttons{display:grid;grid-template-columns:minmax(0,1fr) 78px}.catalog-buttons a,.catalog-buttons button{width:auto;padding:0 7px}}
</style>
