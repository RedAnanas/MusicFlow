export interface AudioInfo {
  format: string
  duration: number
  bitrate: number
  size: number
  codec: string
  sampleRate: number
  channels: number
  bitDepth?: number
}

export interface Metadata {
  title?: string
  artist?: string
  album?: string
  albumArtist?: string
  composer?: string
  genre?: string
  date?: string
  track?: string
  disc?: string
  comment?: string
  copyright?: string
  lyrics?: string
  cover?: {
    data: string | number[]
    mime: string
  }
}

export interface FileItem {
  id: string
  path: string
  filename: string
  format: string
  size: number
  duration?: number
  sampleRate?: number
  bitDepth?: number
  bitrate?: number
  channels?: number
  artist?: string
  album?: string
  title?: string
  track?: string
  year?: string
  genre?: string
  isrc?: string
}

export interface FileSystemEntry {
  name: string
  path: string
  is_directory: boolean
  size?: number
}

export interface LibrarySource {
  id: string
  path: string
  is_directory: boolean
  exists: boolean
}

export interface Profile {
  id: string
  name: string
  enabled: boolean
  outputFormat: 'm4a' | 'mp3' | 'flac' | 'alac' | 'wav' | 'ogg' | 'opus'
  codec?: string
  bitrate?: number
  sampleRate?: number
  channels?: number
  bitDepth?: number
  metadataPolicy: 'keep' | 'overwrite' | 'strip'
  coverPolicy: 'keep' | 'embed' | 'keep_and_embed' | 'strip'
  filenameTemplate: string
  directoryTemplate: string
  outputDir?: string
  appleMusicHandoffEnabled: boolean
  appleMusicDeliveryMode: 'none' | 'client_import' | 'direct_upload'
  appleMusicImportDir?: string
  version: number
}

export interface Task {
  id: string
  source_file: string
  output_file: string
  profile_id: string
  status: 'waiting' | 'converting' | 'success' | 'failed' | 'cancelled' | 'skipped'
  progress?: number
  start_time?: string
  end_time?: string
  error?: string
  apple_music_status?: 'waiting' | 'received' | 'failed' | 'delivery_pending'
  apple_music_delivery_mode?: string
  apple_music_upload?: AppleMusicUpload
  apple_music_import_file?: string
  apple_music_error?: string
}

export interface AppleMusicUpload {
  id: string
  state: string
  stage?: string
  signature_progress?: number | null
  signature_elapsed_seconds?: number | null
  error?: string
  error_code?: string
  allowed_actions: string[]
  running?: boolean
  deleted?: boolean
  can_stop?: boolean
  can_delete?: boolean
  sources?: { conversion_task_id: string; source_file: string; profile_name?: string }[]
  created_at: number
  updated_at: number
  finished_at?: number | null
  elapsed_seconds: number
  server_time: number
  timeline?: UploadTiming[]
}

export interface UploadTiming {
  stage?: string
  state: string
  started_at: number
  ended_at?: number | null
  elapsed_seconds: number
  progress?: number | null
  wait_until?: number | null
  bytes_sent?: number | null
  bytes_total?: number | null
}

export interface WatchFolder {
  id: string
  name: string
  inputDir: string
  defaultTarget: 'all' | 'nas' | 'apple' | 'both'
  profileIds: string[]
  targets: DeliveryTarget[]
  autoProcess: boolean
  recursiveScan: boolean
  scanIntervalMinutes: number
  outputDir?: string
  enabled: boolean
  watching: boolean
  lastScan?: string
  lastScanCount: number
  lastEvent?: string
  lastError?: string
  nextScanAt?: string
  createdTasks: number
  copiedFiles: number
}

export interface DeliveryTarget {
  type: 'convert' | 'copy'
  outputDir: string
  profileId?: string
  library?: 'nas' | 'apple'
}

export interface WatchFolderEvent {
  timestamp: string
  type: string
  message: string
}

export interface Settings {
  musicSourceDir: string
  musicOutputDir: string
  musicArchiveDir: string
  maxConcurrentTasks: number
  ffmpegThreads: number
  fileStableSeconds: number
}

export interface LogEntry {
  timestamp: string
  level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG'
  module: string
  message: string
  details?: string
}

export interface PlayerTrack {
  token: string
  song_name: string
  singers: string
  cover_url?: string
  stream_url: string
  lyrics_url?: string
}
