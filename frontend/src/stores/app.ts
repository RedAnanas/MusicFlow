import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'
import type { FileItem, Task, Profile, WatchFolder, Settings, LogEntry } from '../types'

export const useAppStore = defineStore('app', () => {
  // 状态
  const files = ref<FileItem[]>([])
  const tasks = ref<Task[]>([])
  const profiles = ref<Profile[]>([])
  const watchFolders = ref<WatchFolder[]>([])
  const settings = ref<Settings>({
    musicSourceDir: '/music/source',
    musicOutputDir: '/music/output',
    musicArchiveDir: '/music/archive',
    maxConcurrentTasks: 2,
    ffmpegThreads: 2,
    fileStableSeconds: 30,
  })
  const logs = ref<LogEntry[]>([])

  // 加载状态
  const loading = ref(false)

  // 文件操作
  async function fetchFiles() {
    loading.value = true
    try {
      const response = await axios.get('/api/files/')
      files.value = response.data
    } catch (error) {
      console.error('Failed to fetch files:', error)
    } finally {
      loading.value = false
    }
  }

  // 任务操作
  async function fetchTasks() {
    loading.value = true
    try {
      const response = await axios.get('/api/tasks/')
      tasks.value = response.data
    } catch (error) {
      console.error('Failed to fetch tasks:', error)
    } finally {
      loading.value = false
    }
  }

  // Profile 操作
  async function fetchProfiles() {
    loading.value = true
    try {
      const response = await axios.get('/api/profiles/')
      // 转换字段名从下划线到驼峰格式
      profiles.value = response.data.map((p: any) => ({
        id: p.id,
        name: p.name,
        enabled: p.enabled,
        outputFormat: p.output_format,
        codec: p.codec,
        bitrate: p.bitrate,
        sampleRate: p.sample_rate,
        channels: p.channels,
        bitDepth: p.bit_depth,
        metadataPolicy: p.metadata_policy,
        coverPolicy: p.cover_policy,
        filenameTemplate: p.filename_template,
        directoryTemplate: p.directory_template,
        outputDir: p.output_dir,
      }))
    } catch (error) {
      console.error('Failed to fetch profiles:', error)
    } finally {
      loading.value = false
    }
  }

  async function createProfile(profile: Partial<Profile>) {
    try {
      // 转换字段名为下划线格式
      const apiData: Record<string, any> = {
        name: profile.name,
        enabled: profile.enabled ?? true,
        output_format: profile.outputFormat,
        codec: profile.codec,
        bitrate: profile.bitrate,
        sample_rate: profile.sampleRate,
        metadata_policy: profile.metadataPolicy,
        cover_policy: profile.coverPolicy,
        filename_template: profile.filenameTemplate,
        directory_template: profile.directoryTemplate,
      }

      console.log('Creating profile with data:', apiData)
      const response = await axios.post('/api/profiles/', apiData)

      // 转换响应字段名到驼峰格式
      const newProfile = {
        id: response.data.id,
        name: response.data.name,
        enabled: response.data.enabled,
        outputFormat: response.data.output_format,
        codec: response.data.codec,
        bitrate: response.data.bitrate,
        sampleRate: response.data.sample_rate,
        channels: response.data.channels,
        bitDepth: response.data.bit_depth,
        metadataPolicy: response.data.metadata_policy,
        coverPolicy: response.data.cover_policy,
        filenameTemplate: response.data.filename_template,
        directoryTemplate: response.data.directory_template,
        outputDir: response.data.output_dir,
      }

      profiles.value.push(newProfile)
      return newProfile
    } catch (error) {
      console.error('Failed to create profile:', error)
      throw error
    }
  }

  async function updateProfile(id: string, profile: Partial<Profile>) {
    try {
      // 转换字段名为下划线格式
      const apiData: Record<string, any> = {}
      if (profile.name) apiData.name = profile.name
      if (profile.outputFormat) apiData.output_format = profile.outputFormat
      if (profile.codec) apiData.codec = profile.codec
      if (profile.bitrate) apiData.bitrate = profile.bitrate
      if (profile.sampleRate) apiData.sample_rate = profile.sampleRate
      if (profile.metadataPolicy) apiData.metadata_policy = profile.metadataPolicy
      if (profile.coverPolicy) apiData.cover_policy = profile.coverPolicy
      if (profile.filenameTemplate) apiData.filename_template = profile.filenameTemplate
      if (profile.directoryTemplate) apiData.directory_template = profile.directoryTemplate

      console.log('Store: Updating profile', id, apiData)
      const response = await axios.put(`/api/profiles/${id}`, apiData)
      console.log('Store: Profile updated successfully', response.data)

      // 转换响应字段名到驼峰格式
      const updatedProfile = {
        id: response.data.id,
        name: response.data.name,
        enabled: response.data.enabled,
        outputFormat: response.data.output_format,
        codec: response.data.codec,
        bitrate: response.data.bitrate,
        sampleRate: response.data.sample_rate,
        channels: response.data.channels,
        bitDepth: response.data.bit_depth,
        metadataPolicy: response.data.metadata_policy,
        coverPolicy: response.data.cover_policy,
        filenameTemplate: response.data.filename_template,
        directoryTemplate: response.data.directory_template,
        outputDir: response.data.output_dir,
      }

      const index = profiles.value.findIndex(p => p.id === id)
      if (index !== -1) {
        profiles.value[index] = updatedProfile
      }
      return updatedProfile
    } catch (error: any) {
      console.error('Failed to update profile:', error)
      if (error.response) {
        console.error('Response data:', error.response.data)
        console.error('Response status:', error.response.status)
      }
      throw error
    }
  }

  async function deleteProfile(id: string) {
    try {
      await axios.delete(`/api/profiles/${id}`)
      profiles.value = profiles.value.filter(p => p.id !== id)
    } catch (error) {
      console.error('Failed to delete profile:', error)
      throw error
    }
  }

  // 监控目录操作
  async function fetchWatchFolders() {
    loading.value = true
    try {
      const response = await axios.get('/api/watch-folders/')
      watchFolders.value = response.data
    } catch (error) {
      console.error('Failed to fetch watch folders:', error)
    } finally {
      loading.value = false
    }
  }

  async function createWatchFolder(folder: Partial<WatchFolder>) {
    try {
      // 转换字段名为下划线格式
      const apiData: Record<string, any> = {
        name: folder.name,
        input_dir: folder.inputDir,
        profile_ids: folder.profileIds,
        auto_process: folder.autoProcess,
        recursive_scan: folder.recursiveScan,
        scan_interval_minutes: folder.scanIntervalMinutes,
      }

      console.log('Creating watch folder:', apiData)
      const response = await axios.post('/api/watch-folders/', apiData)

      // 转换响应字段名到驼峰格式
      const newFolder = {
        id: response.data.id,
        name: response.data.name,
        inputDir: response.data.input_dir,
        profileIds: response.data.profile_ids,
        autoProcess: response.data.auto_process,
        recursiveScan: response.data.recursive_scan,
        scanIntervalMinutes: response.data.scan_interval_minutes,
        enabled: response.data.enabled,
        lastScan: response.data.last_scan,
      }

      watchFolders.value.push(newFolder)
      return newFolder
    } catch (error) {
      console.error('Failed to create watch folder:', error)
      throw error
    }
  }

  async function deleteWatchFolder(id: string) {
    try {
      await axios.delete(`/api/watch-folders/${id}`)
      watchFolders.value = watchFolders.value.filter(f => f.id !== id)
    } catch (error) {
      console.error('Failed to delete watch folder:', error)
      throw error
    }
  }

  async function updateWatchFolder(id: string, folder: Partial<WatchFolder>) {
    try {
      // 转换字段名为下划线格式
      const apiData: Record<string, any> = {}
      if (folder.name) apiData.name = folder.name
      if (folder.inputDir) apiData.input_dir = folder.inputDir
      if (folder.profileIds) apiData.profile_ids = folder.profileIds
      if (folder.autoProcess !== undefined) apiData.auto_process = folder.autoProcess
      if (folder.recursiveScan !== undefined) apiData.recursive_scan = folder.recursiveScan
      if (folder.scanIntervalMinutes) apiData.scan_interval_minutes = folder.scanIntervalMinutes

      console.log('Updating watch folder:', id, apiData)
      const response = await axios.put(`/api/watch-folders/${id}`, apiData)

      // 转换响应字段名到驼峰格式
      const updatedFolder = {
        id: response.data.id,
        name: response.data.name,
        inputDir: response.data.input_dir,
        profileIds: response.data.profile_ids,
        autoProcess: response.data.auto_process,
        recursiveScan: response.data.recursive_scan,
        scanIntervalMinutes: response.data.scan_interval_minutes,
        enabled: response.data.enabled,
        lastScan: response.data.last_scan,
      }

      const index = watchFolders.value.findIndex(f => f.id === id)
      if (index !== -1) {
        watchFolders.value[index] = updatedFolder
      }
      return updatedFolder
    } catch (error) {
      console.error('Failed to update watch folder:', error)
      throw error
    }
  }

  async function scanWatchFolder(id: string) {
    try {
      const response = await axios.post(`/api/watch-folders/${id}/scan`)
      return response.data
    } catch (error) {
      console.error('Failed to scan watch folder:', error)
      throw error
    }
  }

  // 设置操作
  async function fetchSettings() {
    loading.value = true
    try {
      const response = await axios.get('/api/settings/')
      settings.value = response.data
    } catch (error) {
      console.error('Failed to fetch settings:', error)
    } finally {
      loading.value = false
    }
  }

  async function updateSettings(newSettings: Partial<Settings>) {
    try {
      const response = await axios.put('/api/settings/', newSettings)
      settings.value = { ...settings.value, ...newSettings }
      return response.data
    } catch (error) {
      console.error('Failed to update settings:', error)
      throw error
    }
  }

  // 日志操作
  async function fetchLogs(limit: number = 100) {
    loading.value = true
    try {
      const response = await axios.get('/api/logs/', { params: { limit } })
      logs.value = response.data
    } catch (error) {
      console.error('Failed to fetch logs:', error)
    } finally {
      loading.value = false
    }
  }

  return {
    files,
    tasks,
    profiles,
    watchFolders,
    settings,
    logs,
    loading,
    fetchFiles,
    fetchTasks,
    fetchProfiles,
    createProfile,
    updateProfile,
    deleteProfile,
    fetchWatchFolders,
    fetchSettings,
    updateSettings,
    fetchLogs,
  }
})
