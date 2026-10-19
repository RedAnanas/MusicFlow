import type { AppleMusicUpload } from '../types'

export const uploadStateLabel = (value: string) => ({
  queued: '等待上传', waiting_worker: '等待上传执行器就绪', waiting_authorization: '需要重新获取并导入桌面授权',
  waiting_client_exit: '等待退出官方客户端', staging: '获取成品', validating: '校验成品', uploading: '上传中',
  cloud_processing: '等待云端处理', media_completed_extras_pending: '音频完成，歌词或封面待处理',
  cloud_completed: '云端协议完成，待快照确认', requires_review: '结果不确定，需要人工核对',
  failed: '上传失败', cancelled: '已取消排队', stopping: '正在停止', stopped: '已停止，可恢复',
}[value] || value)

export const uploadStageLabel = (value?: string) => ({ queued: '排队等待', download: '获取上传成品', validation: '校验成品及上传环境', 'session-wait': '等待前一首完成 Apple 上传会话', media: '解析音频及提取歌词封面', hash: '计算音频哈希', decode: '解码指纹音频', partial: '局部音频指纹', 'full-lowres': '全曲指纹（音频处理进度）', signature: '生成签名', 'fingerprint-upload': '提交指纹', 'prepare-track': '准备音频资产', waiting: '等待 Apple 下发任务', 'extras-waiting': '等待歌词封面处理', metadata: '提交元数据', audio: '上传音频资产', extras: '处理歌词封面', processing: '协议处理', complete: '完成' }[value || ''] || '')

export const uploadActionLabel = (value: string) => value === 'upload_media_extras' ? '补传歌词封面' : value === 'upload' ? '重试上传成品' : '恢复上传'

export const uploadSignatureProgress = (upload: AppleMusicUpload) => {
  if (upload.stage !== 'signature' || upload.signature_progress == null) return ''
  const seconds = Math.floor(upload.signature_elapsed_seconds || 0)
  return ` ${upload.signature_progress}% · 已耗时 ${Math.floor(seconds / 60)}分${seconds % 60}秒`
}
