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
  apple_music_status?: 'waiting' | 'received' | 'failed'
  apple_music_import_file?: string
  apple_music_error?: string
}

export interface WatchFolder {
  id: string
  name: string
  inputDir: string
  profileIds: string[]
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
