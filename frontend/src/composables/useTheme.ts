import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const storageKey = 'musicflow-theme-mode'
const themeMode = ref<ThemeMode>(readThemeMode())
const systemTheme = window.matchMedia('(prefers-color-scheme: dark)')

function readThemeMode(): ThemeMode {
  const savedMode = window.localStorage.getItem(storageKey)
  return savedMode === 'light' || savedMode === 'dark' || savedMode === 'system' ? savedMode : 'system'
}

function applyTheme() {
  const activeTheme = themeMode.value === 'system'
    ? (systemTheme.matches ? 'dark' : 'light')
    : themeMode.value
  document.documentElement.classList.toggle('dark', activeTheme === 'dark')
  document.documentElement.style.colorScheme = activeTheme
}

function setTheme(mode: ThemeMode) {
  themeMode.value = mode
  window.localStorage.setItem(storageKey, mode)
  applyTheme()
}

systemTheme.addEventListener('change', () => {
  if (themeMode.value === 'system') applyTheme()
})

applyTheme()

export function useTheme() {
  return {
    themeMode: computed(() => themeMode.value),
    setTheme,
  }
}
