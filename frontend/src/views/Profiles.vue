<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Profile } from '../types'

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

onMounted(() => {
  store.fetchProfiles()
})

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
  <div class="profiles-page">
    <div class="page-header">
      <h1>转换配置</h1>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        创建配置
      </el-button>
    </div>

    <!-- 转换配置列表 -->
    <el-card v-loading="store.loading">
      <el-table :data="store.profiles" style="width: 100%">
        <el-table-column prop="name" label="名称" min-width="160" />

        <el-table-column prop="outputFormat" label="输出格式" width="100">
          <template #default="{ row }">
            <el-tag>{{ row.outputFormat?.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="codec" label="编码器" width="120" />

        <el-table-column prop="bitrate" label="比特率" width="100">
          <template #default="{ row }">
            {{ row.bitrate ? row.bitrate + ' kbps' : '--' }}
          </template>
        </el-table-column>

        <el-table-column prop="sampleRate" label="采样率" width="100">
          <template #default="{ row }">
            {{ row.sampleRate ? row.sampleRate + ' Hz' : '保持源文件' }}
          </template>
        </el-table-column>

        <el-table-column prop="channels" label="声道数" width="110">
          <template #default="{ row }">
            {{ row.channels ? row.channels + ' 声道' : '保持源文件' }}
          </template>
        </el-table-column>

        <el-table-column prop="bitDepth" label="位深" width="110">
          <template #default="{ row }">
            {{ row.bitDepth ? row.bitDepth + ' bit' : '保持源文件' }}
          </template>
        </el-table-column>

        <el-table-column prop="metadataPolicy" label="元数据策略" width="120">
          <template #default="{ row }">
            {{ getMetadataPolicyLabel(row.metadataPolicy) }}
          </template>
        </el-table-column>

        <el-table-column prop="coverPolicy" label="封面策略" width="130">
          <template #default="{ row }">
            {{ getCoverPolicyLabel(row.coverPolicy) }}
          </template>
        </el-table-column>

        <el-table-column label="Apple Music" width="130">
          <template #default="{ row }">
            <el-tag v-if="row.appleMusicHandoffEnabled" type="success" size="small">自动交接</el-tag>
            <span v-else>未启用</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleEdit(row)">
              编辑
            </el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row.id)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑对话框 -->
    <el-dialog
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
  </div>
</template>

<style scoped>
.profiles-page {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

h1 {
  margin: 0;
  color: #303133;
}

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
  color: #409eff;
  border-left: 3px solid #409eff;
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

@media (max-width: 700px) {
  .profile-form {
    grid-template-columns: 1fr;
  }
}
</style>
