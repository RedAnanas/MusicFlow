<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Profile } from '../types'
import ProfileEditorDialog from '../components/ProfileEditorDialog.vue'

const store = useAppStore()
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const selectedProfile = ref<Profile | null>(null)

interface ProfileForm {
  name: string
  outputFormat: Profile['outputFormat']
  codec: string
  bitrate: number
  sampleRate: number
  metadataPolicy: Profile['metadataPolicy']
  coverPolicy: Profile['coverPolicy']
  filenameTemplate: string
  directoryTemplate: string
  appleMusicHandoffEnabled: boolean
  appleMusicImportDir: string
}

const createDefaultProfileForm = (): ProfileForm => ({
  name: '',
  outputFormat: 'm4a',
  codec: 'aac',
  bitrate: 256,
  sampleRate: 44100,
  metadataPolicy: 'keep',
  coverPolicy: 'embed',
  filenameTemplate: '{title}.{extension}',
  directoryTemplate: '{album_artist}/{year} - {album}',
  appleMusicHandoffEnabled: false,
  appleMusicImportDir: '',
})

const newProfile = ref<ProfileForm>(createDefaultProfileForm())
const editProfile = ref<ProfileForm>(createDefaultProfileForm())

const bitrateOptions = [
  { label: '64 kbps', value: 64 },
  { label: '96 kbps', value: 96 },
  { label: '128 kbps', value: 128 },
  { label: '160 kbps', value: 160 },
  { label: '192 kbps', value: 192 },
  { label: '224 kbps', value: 224 },
  { label: '256 kbps', value: 256 },
  { label: '320 kbps', value: 320 },
]

const codecOptions = [
  { label: 'AAC (推荐)', value: 'aac' },
  { label: 'ALAC (无损)', value: 'alac' },
  { label: 'MP3 (libmp3lame)', value: 'libmp3lame' },
  { label: 'FLAC (无损)', value: 'flac' },
  { label: 'Vorbis', value: 'libvorbis' },
  { label: 'Opus', value: 'libopus' },
  { label: 'PCM (WAV)', value: 'pcm_s16le' },
]

const metadataPolicyLabels: Record<Profile['metadataPolicy'], string> = {
  keep: '保留',
  overwrite: '覆盖',
  strip: '不写入',
}

const coverPolicyLabels: Record<Profile['coverPolicy'], string> = {
  keep: '保留',
  embed: '嵌入',
  keep_and_embed: '保留并嵌入',
  strip: '不处理',
}

const getMetadataPolicyLabel = (policy: Profile['metadataPolicy']) => {
  return metadataPolicyLabels[policy] || policy
}

const getCoverPolicyLabel = (policy: Profile['coverPolicy']) => {
  return coverPolicyLabels[policy] || policy
}

onMounted(async () => {
  await Promise.all([store.fetchProfiles(), store.fetchFiles()])
})

watch(
  () => store.profiles,
  profiles => {
    if (!profiles.length) {
      selectedProfile.value = null
      return
    }
    selectedProfile.value = profiles.find(profile => profile.id === selectedProfile.value?.id) || profiles[0]
  },
  { immediate: true, deep: true },
)

const previewFile = computed(() => store.files[0])
const previewCoverUrl = computed(() => previewFile.value ? `/api/files/${previewFile.value.id}/cover` : '')
const previewFilename = computed(() => {
  const profile = selectedProfile.value
  const file = previewFile.value
  if (!profile) return '--'
  const title = file?.title || file?.filename?.replace(/\.[^.]+$/, '') || '歌曲标题'
  return profile.filenameTemplate.replace('{title}', title).replace('{extension}', profile.outputFormat)
})

const handleDuplicate = (profile: Profile) => {
  newProfile.value = {
    name: `${profile.name} 副本`, outputFormat: profile.outputFormat,
    codec: profile.codec || 'aac', bitrate: profile.bitrate || 256,
    sampleRate: profile.sampleRate || 44100, metadataPolicy: profile.metadataPolicy,
    coverPolicy: profile.coverPolicy, filenameTemplate: profile.filenameTemplate,
    directoryTemplate: profile.directoryTemplate,
    appleMusicHandoffEnabled: profile.appleMusicHandoffEnabled,
    appleMusicImportDir: profile.appleMusicImportDir || '',
  }
  showCreateDialog.value = true
}

const handleCreate = async () => {
  try {
    console.log('Creating profile:', newProfile.value)
    await store.createProfile(newProfile.value)
    showCreateDialog.value = false
    ElMessage.success('转换配置创建成功')
    // 重置表单
    newProfile.value = createDefaultProfileForm()
    // 重新加载列表
    await store.fetchProfiles()
  } catch (error) {
    console.error('Create failed:', error)
    ElMessage.error('创建失败')
  }
}

const handleEdit = (profile: Profile) => {
  selectedProfile.value = profile
  editProfile.value = {
    name: profile.name,
    outputFormat: profile.outputFormat,
    codec: profile.codec || 'aac',
    bitrate: profile.bitrate || 256,
    sampleRate: profile.sampleRate || 44100,
    metadataPolicy: profile.metadataPolicy,
    coverPolicy: profile.coverPolicy,
    filenameTemplate: profile.filenameTemplate,
    directoryTemplate: profile.directoryTemplate,
    appleMusicHandoffEnabled: profile.appleMusicHandoffEnabled,
    appleMusicImportDir: profile.appleMusicImportDir || '',
  }
  showEditDialog.value = true
}

const handleUpdate = async () => {
  if (!selectedProfile.value) return
  try {
    // 构建完整的更新数据
    const updateData = {
      name: editProfile.value.name,
      outputFormat: editProfile.value.outputFormat,
      codec: editProfile.value.codec,
      bitrate: editProfile.value.bitrate,
      sampleRate: editProfile.value.sampleRate,
      metadataPolicy: editProfile.value.metadataPolicy,
      coverPolicy: editProfile.value.coverPolicy,
      filenameTemplate: editProfile.value.filenameTemplate,
      directoryTemplate: editProfile.value.directoryTemplate,
      appleMusicHandoffEnabled: editProfile.value.appleMusicHandoffEnabled,
      appleMusicImportDir: editProfile.value.appleMusicImportDir,
    }

    console.log('Updating profile:', selectedProfile.value.id, updateData)
    await store.updateProfile(selectedProfile.value.id, updateData)
    showEditDialog.value = false
    ElMessage.success('转换配置更新成功')
    // 重新加载列表
    await store.fetchProfiles()
  } catch (error) {
    console.error('Update failed:', error)
    ElMessage.error('更新失败')
  }
}

const handleDelete = async (id: string) => {
  try {
    await ElMessageBox.confirm('确定要删除这个转换配置吗？', '确认', {
      type: 'warning',
    })
    await store.deleteProfile(id)
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}
</script>

<template>
  <div class="profiles-page product-page">
    <div class="page-header">
      <div class="page-title-block">
        <h1>转换方案</h1>
        <p>管理输出格式、音质、元数据和 Apple Music 自动交接规则。</p>
      </div>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        新建方案
      </el-button>
    </div>

    <div class="profile-workspace" v-loading="store.loading">
      <aside class="profile-list-panel">
        <div class="panel-heading"><span>全部方案</span><span class="panel-count">{{ store.profiles.length }}</span></div>
        <button v-for="profile in store.profiles" :key="profile.id" class="profile-list-item" :class="{ active: selectedProfile?.id === profile.id }" type="button" @click="selectedProfile = profile">
          <span class="format-icon">{{ profile.outputFormat.toUpperCase() }}</span>
          <span class="profile-list-copy"><strong>{{ profile.name }}</strong><small>{{ profile.codec?.toUpperCase() || '--' }} · {{ profile.bitrate ? `${profile.bitrate} kbps` : '无损' }}</small></span>
          <el-icon><ArrowRight /></el-icon>
        </button>
        <el-empty v-if="!store.profiles.length" description="还没有转换方案" :image-size="70" />
      </aside>

      <section v-if="selectedProfile" class="profile-inspector">
        <div class="inspector-header">
          <div><div class="eyebrow">方案详情</div><h2>{{ selectedProfile.name }}</h2><p>版本 {{ selectedProfile.version }} · {{ selectedProfile.enabled ? '当前可用' : '已停用' }}</p></div>
          <div class="inspector-actions"><el-button @click="handleDuplicate(selectedProfile)"><el-icon><CopyDocument /></el-icon>复制</el-button><el-button type="primary" @click="handleEdit(selectedProfile)"><el-icon><Edit /></el-icon>编辑方案</el-button></div>
        </div>
        <div class="detail-grid">
          <article class="detail-card">
            <div class="detail-title"><el-icon><Headset /></el-icon><span>音频质量</span></div>
            <dl><div><dt>输出格式</dt><dd><el-tag>{{ selectedProfile.outputFormat.toUpperCase() }}</el-tag></dd></div><div><dt>编码器</dt><dd>{{ selectedProfile.codec?.toUpperCase() || '--' }}</dd></div><div><dt>比特率</dt><dd>{{ selectedProfile.bitrate ? `${selectedProfile.bitrate} kbps` : '保持源文件' }}</dd></div><div><dt>采样率</dt><dd>{{ selectedProfile.sampleRate ? `${selectedProfile.sampleRate} Hz` : '保持源文件' }}</dd></div><div><dt>声道 / 位深</dt><dd>{{ selectedProfile.channels ? `${selectedProfile.channels} 声道` : '保持' }} · {{ selectedProfile.bitDepth ? `${selectedProfile.bitDepth} bit` : '保持' }}</dd></div></dl>
          </article>
          <article class="detail-card">
            <div class="detail-title"><el-icon><Picture /></el-icon><span>元数据与封面</span></div>
            <dl><div><dt>歌曲标签</dt><dd>{{ getMetadataPolicyLabel(selectedProfile.metadataPolicy) }}</dd></div><div><dt>专辑封面</dt><dd>{{ getCoverPolicyLabel(selectedProfile.coverPolicy) }}</dd></div><div><dt>歌词信息</dt><dd>{{ selectedProfile.metadataPolicy === 'strip' ? '不写入' : '随元数据保留' }}</dd></div></dl>
          </article>
          <article class="detail-card wide-card">
            <div class="detail-title"><el-icon><Folder /></el-icon><span>命名与输出</span></div>
            <dl class="path-list"><div><dt>文件名模板</dt><dd><code>{{ selectedProfile.filenameTemplate }}</code></dd></div><div><dt>目录模板</dt><dd><code>{{ selectedProfile.directoryTemplate }}</code></dd></div><div><dt>默认输出目录</dt><dd><code>{{ selectedProfile.outputDir || '使用全局输出目录' }}</code></dd></div></dl>
          </article>
          <article class="detail-card">
            <div class="detail-title"><el-icon><Connection /></el-icon><span>Apple Music</span></div>
            <div class="handoff-state"><span class="status-dot" :class="{ enabled: selectedProfile.appleMusicHandoffEnabled }"></span><div><strong>{{ selectedProfile.appleMusicHandoffEnabled ? '自动交接已开启' : '自动交接未开启' }}</strong><small>{{ selectedProfile.appleMusicImportDir || '转换完成后不会自动导入' }}</small></div></div>
          </article>
          <article class="detail-card preview-card">
            <div class="detail-title"><el-icon><View /></el-icon><span>输出预览</span></div>
            <div class="output-preview"><el-image v-if="previewCoverUrl" :src="previewCoverUrl" fit="cover"><template #error><div class="cover-fallback"><el-icon><Headset /></el-icon></div></template></el-image><div v-else class="cover-fallback"><el-icon><Headset /></el-icon></div><div><strong>{{ previewFilename }}</strong><span>{{ previewFile?.artist || '未知艺术家' }} · {{ previewFile?.album || '未知专辑' }}</span><small>{{ selectedProfile.outputFormat.toUpperCase() }} · {{ selectedProfile.bitrate ? `${selectedProfile.bitrate} kbps` : '无损' }}</small></div></div>
          </article>
        </div>
        <div class="danger-row"><el-button type="danger" link @click="handleDelete(selectedProfile.id)"><el-icon><Delete /></el-icon>删除此方案</el-button></div>
      </section>
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-if="false"
      v-model="showCreateDialog"
      title="创建转换配置"
      width="760px"
    >
      <el-form :model="newProfile" label-position="top" class="profile-form">
        <div class="form-section-title">基础参数</div>
        <el-form-item class="form-item-full">
          <template #label>名称<el-tooltip content="用于在转换任务中识别此配置。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="newProfile.name" placeholder="例如：Apple Music AAC 256" />
        </el-form-item>

        <el-form-item>
          <template #label>输出格式<el-tooltip content="转换完成后生成文件的容器格式和扩展名。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="newProfile.outputFormat">
            <el-option label="M4A" value="m4a" />
            <el-option label="MP3" value="mp3" />
            <el-option label="FLAC" value="flac" />
            <el-option label="ALAC" value="alac" />
            <el-option label="WAV" value="wav" />
            <el-option label="OGG" value="ogg" />
            <el-option label="OPUS" value="opus" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>编码器<el-tooltip content="决定音频如何编码，例如 AAC、ALAC 或 MP3。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="newProfile.codec" filterable placeholder="选择编码器">
            <el-option
              v-for="option in codecOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>比特率<el-tooltip content="有损编码的每秒数据量；数值越高通常音质越好、文件越大。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="newProfile.bitrate">
            <el-option
              v-for="option in bitrateOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>采样率<el-tooltip content="每秒采样次数；留空时保持源文件采样率。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="newProfile.sampleRate" clearable placeholder="保持源文件">
            <el-option label="44100 Hz" :value="44100" />
            <el-option label="48000 Hz" :value="48000" />
            <el-option label="96000 Hz" :value="96000" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>元数据策略<el-tooltip content="控制歌曲标题、艺术家、专辑、歌词等标签的处理方式。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="newProfile.metadataPolicy">
            <el-option label="保留" value="keep" />
            <el-option label="覆盖" value="overwrite" />
            <el-option label="不写入" value="strip" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>封面策略<el-tooltip content="控制是否保留或写入专辑封面。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="newProfile.coverPolicy">
            <el-option label="保留" value="keep" />
            <el-option label="嵌入" value="embed" />
            <el-option label="保留并嵌入" value="keep_and_embed" />
            <el-option label="不处理" value="strip" />
          </el-select>
        </el-form-item>

        <div class="form-section-title form-item-full">标签与命名</div>
        <el-form-item class="form-item-full">
          <template #label>文件名模板<el-tooltip content="定义生成文件的名称；可使用 {title} 和 {extension} 等占位符。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="newProfile.filenameTemplate" placeholder="{title}.{extension}" />
        </el-form-item>

        <el-form-item class="form-item-full">
          <template #label>目录模板<el-tooltip content="定义输出文件的目录层级；可使用艺术家、专辑和年份等占位符。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="newProfile.directoryTemplate" placeholder="{album_artist}/{year} - {album}" />
        </el-form-item>

        <div class="form-section-title form-item-full">Apple Music 交接</div>
        <el-form-item class="form-item-full">
          <template #label>Apple Music 交接<el-tooltip content="转换完成后，将成品复制到 Apple Music 的自动导入目录。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-switch v-model="newProfile.appleMusicHandoffEnabled" />
        </el-form-item>

        <el-form-item v-if="newProfile.appleMusicHandoffEnabled" class="form-item-full">
          <template #label>自动导入目录<el-tooltip content="Apple Music 监控的 Automatically Add to Apple Music 目录。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input
            v-model="newProfile.appleMusicImportDir"
            placeholder="/mnt/d/Music/output/M4A/AAC/Automatically Add to Apple Music"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-if="false"
      v-model="showEditDialog"
      title="编辑转换配置"
      width="760px"
    >
      <el-form :model="editProfile" label-position="top" class="profile-form">
        <div class="form-section-title">基础参数</div>
        <el-form-item class="form-item-full">
          <template #label>名称<el-tooltip content="用于在转换任务中识别此配置。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="editProfile.name" placeholder="例如：Apple Music AAC 256" />
        </el-form-item>

        <el-form-item>
          <template #label>输出格式<el-tooltip content="转换完成后生成文件的容器格式和扩展名。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="editProfile.outputFormat">
            <el-option label="M4A" value="m4a" />
            <el-option label="MP3" value="mp3" />
            <el-option label="FLAC" value="flac" />
            <el-option label="ALAC" value="alac" />
            <el-option label="WAV" value="wav" />
            <el-option label="OGG" value="ogg" />
            <el-option label="OPUS" value="opus" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>编码器<el-tooltip content="决定音频如何编码，例如 AAC、ALAC 或 MP3。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="editProfile.codec" filterable placeholder="选择编码器">
            <el-option
              v-for="option in codecOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>比特率<el-tooltip content="有损编码的每秒数据量；数值越高通常音质越好、文件越大。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="editProfile.bitrate">
            <el-option
              v-for="option in bitrateOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>采样率<el-tooltip content="每秒采样次数；留空时保持源文件采样率。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="editProfile.sampleRate" clearable placeholder="保持源文件">
            <el-option label="44100 Hz" :value="44100" />
            <el-option label="48000 Hz" :value="48000" />
            <el-option label="96000 Hz" :value="96000" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>元数据策略<el-tooltip content="控制歌曲标题、艺术家、专辑、歌词等标签的处理方式。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="editProfile.metadataPolicy">
            <el-option label="保留" value="keep" />
            <el-option label="覆盖" value="overwrite" />
            <el-option label="不写入" value="strip" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <template #label>封面策略<el-tooltip content="控制是否保留或写入专辑封面。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-select v-model="editProfile.coverPolicy">
            <el-option label="保留" value="keep" />
            <el-option label="嵌入" value="embed" />
            <el-option label="保留并嵌入" value="keep_and_embed" />
            <el-option label="不处理" value="strip" />
          </el-select>
        </el-form-item>

        <div class="form-section-title form-item-full">标签与命名</div>
        <el-form-item class="form-item-full">
          <template #label>文件名模板<el-tooltip content="定义生成文件的名称；可使用 {title} 和 {extension} 等占位符。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="editProfile.filenameTemplate" placeholder="{title}.{extension}" />
        </el-form-item>

        <el-form-item class="form-item-full">
          <template #label>目录模板<el-tooltip content="定义输出文件的目录层级；可使用艺术家、专辑和年份等占位符。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input v-model="editProfile.directoryTemplate" placeholder="{album_artist}/{year} - {album}" />
        </el-form-item>

        <div class="form-section-title form-item-full">Apple Music 交接</div>
        <el-form-item class="form-item-full">
          <template #label>Apple Music 交接<el-tooltip content="转换完成后，将成品复制到 Apple Music 的自动导入目录。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-switch v-model="editProfile.appleMusicHandoffEnabled" />
        </el-form-item>

        <el-form-item v-if="editProfile.appleMusicHandoffEnabled" class="form-item-full">
          <template #label>自动导入目录<el-tooltip content="Apple Music 监控的 Automatically Add to Apple Music 目录。" placement="top"><el-icon class="field-help"><QuestionFilled /></el-icon></el-tooltip></template>
          <el-input
            v-model="editProfile.appleMusicImportDir"
            placeholder="/mnt/d/Music/output/M4A/AAC/Automatically Add to Apple Music"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUpdate">更新</el-button>
      </template>
    </el-dialog>

    <ProfileEditorDialog v-model="showCreateDialog" mode="create" :form="newProfile" :preview-file="previewFile" @submit="handleCreate" />
    <ProfileEditorDialog v-model="showEditDialog" mode="edit" :form="editProfile" :preview-file="previewFile" @submit="handleUpdate" />
  </div>
</template>

<style scoped>
.profiles-page {
  padding-bottom: 32px;
}

.profile-workspace { display: grid; grid-template-columns: 286px minmax(0, 1fr); min-height: 650px; overflow: hidden; background: #fff; border: 1px solid #e8ecea; border-radius: 16px; box-shadow: 0 12px 36px rgba(18, 58, 45, .06); }
.profile-list-panel { padding: 18px 12px; background: #f8faf9; border-right: 1px solid #e8ecea; }
.panel-heading { display: flex; align-items: center; justify-content: space-between; padding: 0 10px 14px; color: #606b67; font-size: 13px; font-weight: 700; }
.panel-count { display: inline-grid; min-width: 24px; height: 24px; place-items: center; background: #e8f5f0; color: #087955; border-radius: 12px; }
.profile-list-item { display: flex; width: 100%; align-items: center; gap: 12px; padding: 13px 12px; margin-bottom: 6px; color: #33413c; text-align: left; background: transparent; border: 1px solid transparent; border-radius: 12px; cursor: pointer; }
.profile-list-item:hover { background: #fff; }
.profile-list-item.active { background: #fff; border-color: #cce8dd; box-shadow: 0 6px 18px rgba(18, 94, 70, .08); }
.format-icon { display: grid; width: 42px; height: 42px; flex: 0 0 42px; place-items: center; background: #e2f3ed; color: #087955; border-radius: 10px; font-size: 10px; font-weight: 800; }
.profile-list-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 4px; }
.profile-list-copy strong { overflow: hidden; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.profile-list-copy small { color: #8a9691; font-size: 11px; }
.profile-list-item > .el-icon { color: #9aa6a1; }
.profile-list-item.active > .el-icon { color: #0c9c68; }
.profile-inspector { min-width: 0; padding: 26px 28px; }
.inspector-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding-bottom: 22px; border-bottom: 1px solid #edf0ef; }
.eyebrow { margin-bottom: 6px; color: #0c9c68; font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.inspector-header h2 { margin: 0; color: #1d2925; font-size: 24px; }
.inspector-header p { margin: 7px 0 0; color: #89948f; font-size: 13px; }
.inspector-actions { display: flex; gap: 8px; }
.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; padding-top: 20px; }
.detail-card { min-width: 0; padding: 18px; background: #fbfcfc; border: 1px solid #e9eeeb; border-radius: 13px; }
.wide-card { grid-column: 1 / -1; }
.detail-title { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; color: #25332e; font-size: 14px; font-weight: 700; }
.detail-title .el-icon { color: #0c9c68; font-size: 17px; }
dl { margin: 0; }
dl > div { display: flex; align-items: center; justify-content: space-between; gap: 16px; min-height: 32px; border-bottom: 1px dashed #e3e8e5; }
dl > div:last-child { border-bottom: 0; }
dt { color: #87918d; font-size: 12px; }
dd { margin: 0; color: #2f3b37; font-size: 13px; font-weight: 600; text-align: right; }
.path-list dd { max-width: 70%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
code { padding: 4px 7px; background: #edf3f0; color: #385148; border-radius: 5px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; }
.handoff-state { display: flex; align-items: flex-start; gap: 11px; }
.status-dot { width: 9px; height: 9px; margin-top: 5px; background: #b8c0bd; border-radius: 50%; box-shadow: 0 0 0 4px #eff2f1; }
.status-dot.enabled { background: #0c9c68; box-shadow: 0 0 0 4px #e1f4ed; }
.handoff-state div, .output-preview > div:last-child { display: flex; min-width: 0; flex-direction: column; gap: 5px; }
.handoff-state strong, .output-preview strong { font-size: 13px; }
.handoff-state small, .output-preview span, .output-preview small { overflow: hidden; color: #8b9691; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.output-preview { display: flex; align-items: center; gap: 12px; }
.output-preview :deep(.el-image), .cover-fallback { width: 58px; height: 58px; flex: 0 0 58px; overflow: hidden; border-radius: 9px; }
.cover-fallback { display: grid; place-items: center; background: linear-gradient(145deg, #d9eee7, #edf4f1); color: #0c9c68; font-size: 22px; }
.output-preview strong, .output-preview span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.danger-row { display: flex; justify-content: flex-end; padding-top: 14px; }

.form-tip {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
}

.profile-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 20px;
}

.profile-form :deep(.el-form-item) {
  min-width: 0;
  margin-bottom: 18px;
}

.profile-form :deep(.el-form-item__label) {
  width: auto !important;
  height: auto;
  padding: 0 0 8px;
  color: #303133;
  font-weight: 500;
  line-height: 20px;
}

.profile-form :deep(.el-form-item__content) {
  min-width: 0;
}

.form-item-full {
  grid-column: 1 / -1;
}

.form-section-title {
  grid-column: 1 / -1;
  margin: 4px 0 14px;
  padding-left: 10px;
  color: #0c9c68;
  border-left: 3px solid #0c9c68;
  font-size: 15px;
  font-weight: 600;
  line-height: 20px;
}

.field-help {
  margin-left: 4px;
  color: #909399;
  cursor: help;
  vertical-align: -2px;
}

:deep(.el-card__body) {
  overflow: hidden;
  border-radius: 12px;
}

:deep(.el-dialog) {
  border-radius: 14px;
}

@media (max-width: 700px) {
  .profile-workspace { grid-template-columns: 1fr; }
  .profile-list-panel { border-right: 0; border-bottom: 1px solid #e8ecea; }
  .profile-inspector { padding: 20px; }
  .inspector-header { flex-direction: column; }
  .detail-grid { grid-template-columns: 1fr; }
  .wide-card { grid-column: auto; }
  .profile-form {
    grid-template-columns: 1fr;
  }
}
</style>
