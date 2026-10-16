import type { AppleMusicUpload } from '../types'

export const uploadStateLabel = (value: string) => ({
  queued: '等待上传', waiting_worker: '等待上传执行器就绪', waiting_authorization: '需要重新获取并导入桌面授权',
  waiting_client_exit: '等待退出官方客户端', staging: '获取成品', validating: '校验成品', uploading: '上传中',
  cloud_processing: '等待云端处理', media_completed_extras_pending: '音频完成，歌词或封面待处理',
  cloud_completed: '云端协议完成，待快照确认', requires_review: '结果不确定，需要人工核对',
  failed: '上传失败', cancelled: '已停止后续处理',
}[value] || value)

export const uploadStageLabel = (value?: string) => ({ download: '下载成品', validation: '校验成品', signature: '生成或提交签名', metadata: '提交元数据', audio: '上传音频资产', extras: '处理歌词封面', processing: '协议处理', complete: '完成' }[value || ''] || '')

export const uploadActionLabel = (value: string) => value === 'upload_media_extras' ? '补传歌词封面' : value === 'upload' ? '重试上传成品' : '恢复上传'

export const uploadSignatureProgress = (upload: AppleMusicUpload) => {
  if (upload.stage !== 'signature' || upload.signature_progress == null) return ''
  const seconds = Math.floor(upload.signature_elapsed_seconds || 0)
  return ` ${upload.signature_progress}% · 已耗时 ${Math.floor(seconds / 60)}分${seconds % 60}秒`
}
