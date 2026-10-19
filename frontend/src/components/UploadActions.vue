<script setup lang="ts">
import { ref } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AppleMusicUpload } from '../types'
import { uploadActionLabel } from '../utils/appleMusicUpload'

const props = defineProps<{ upload: AppleMusicUpload; conversionTaskId?: string }>()
const emit = defineEmits<{ changed: [] }>()
const busy = ref(false)
const queued = ['queued', 'waiting_worker', 'waiting_authorization', 'waiting_client_exit']
async function act(action: 'cancel' | 'stop' | 'retry' | 'delete') {
  try {
    if (action === 'stop') await ElMessageBox.confirm(`停止本地执行不会撤回 Apple 已接收的请求，后续能否恢复取决于检查点。${props.upload.sources && props.upload.sources.length > 1 ? `此任务关联 ${props.upload.sources.length} 条转换记录，将一起停止。` : ''}`, '停止上传', { confirmButtonText: '停止上传', cancelButtonText: '返回', type: 'warning' })
    if (action === 'delete') await ElMessageBox.confirm(props.conversionTaskId ? '仅隐藏当前转换记录的上传关联，保留成品、云端歌曲及防重复记录。' : '隐藏此上传记录及所有来源中的上传展示，保留成品、云端歌曲及防重复记录。', '删除上传记录', { confirmButtonText: '删除记录', cancelButtonText: '返回', type: 'warning' })
    busy.value = true
    const path = `/api/apple-music/uploads/${props.upload.id}`
    if (action === 'delete') await axios.delete(path, { params: { conversion_task_id: props.conversionTaskId } })
    else await axios.post(`${path}/${action}`, action === 'retry' ? { action: props.upload.allowed_actions[0] } : undefined)
    ElMessage.success(action === 'stop' ? '已请求停止，等待任务进程退出' : action === 'retry' ? '已重新进入上传队列' : action === 'delete' ? '上传记录已隐藏' : '已取消排队')
    emit('changed')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.detail || '操作失败，请重试' : '操作失败，请重试')
  } finally { busy.value = false }
}
</script>

<template>
  <span v-if="!upload.deleted" class="upload-actions">
    <el-button v-if="queued.includes(upload.state)" :disabled="busy" link type="danger" @click="act('cancel')">取消排队</el-button>
    <el-button v-if="upload.can_stop" :disabled="busy" link type="danger" @click="act('stop')">停止上传</el-button>
    <span v-if="upload.state === 'stopping'">正在停止，等待进程退出</span>
    <el-button v-if="upload.allowed_actions.length" :disabled="busy" link type="primary" @click="act('retry')">{{ uploadActionLabel(upload.allowed_actions[0]) }}</el-button>
    <span v-if="upload.state === 'requires_review'">请核对 Apple Music 曲库与受保护记录，结果不确定时不能重传</span>
    <el-button v-if="upload.can_delete" :disabled="busy" link type="danger" @click="act('delete')">删除记录</el-button>
  </span>
</template>

<style scoped>
.upload-actions { display:inline-flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:12px; }
</style>
