<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Document, Files, FolderOpened, House, Monitor, Moon, Setting, Sunny } from '@element-plus/icons-vue'
import { type ThemeMode, useTheme } from './composables/useTheme'

const route = useRoute()
const { themeMode, setTheme } = useTheme()
const appVersion = __MUSICFLOW_VERSION__
const navItems = [
  { path: '/', label: '首页', icon: House },
  { path: '/files', label: '操作台', icon: Files },
  { path: '/tasks', label: '操作记录', icon: Document },
  { path: '/profiles', label: '转换方案', icon: Document },
  { path: '/watch-folders', label: '监控目录', icon: FolderOpened },
  { path: '/system', label: '系统设置', icon: Setting },
]
const mobileNavItems = navItems.filter(item => ['/', '/files', '/tasks', '/profiles', '/watch-folders', '/system'].includes(item.path))
const themeOptions = [
  { value: 'light' as const, label: '日间模式', icon: Sunny },
  { value: 'dark' as const, label: '夜间模式', icon: Moon },
  { value: 'system' as const, label: '跟随系统', icon: Monitor },
]
const currentTheme = computed(() => themeOptions.find(option => option.value === themeMode.value)!)

function selectTheme(mode: ThemeMode) {
  setTheme(mode)
}
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink to="/" class="brand" aria-label="MusicFlow 首页"><img class="brand-mark" src="/musicflow-icon.png" alt="" /><span>MusicFlow</span><small>v{{ appVersion }}</small></RouterLink>
      <nav class="main-nav" aria-label="主导航"><RouterLink v-for="item in navItems" :key="item.path" :to="item.path" :class="{ active: route.path === item.path }">{{ item.label }}</RouterLink></nav>
      <div class="top-actions">
        <el-dropdown trigger="click" @command="selectTheme">
          <el-button text circle class="theme-button" :aria-label="`主题：${currentTheme.label}`" :title="`主题：${currentTheme.label}`">
            <el-icon><component :is="currentTheme.icon" /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu class="theme-menu">
              <el-dropdown-item v-for="option in themeOptions" :key="option.value" :command="option.value" :class="{ active: option.value === themeMode }">
                <el-icon><component :is="option.icon" /></el-icon><span>{{ option.label }}</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button text circle aria-label="通知"><el-icon><Bell /></el-icon></el-button><span class="service-avatar" title="本地服务"><el-icon><Connection /></el-icon></span>
      </div>
    </header>
    <main class="app-main"><RouterView /></main>
    <nav class="mobile-nav" aria-label="移动端主导航"><RouterLink v-for="item in mobileNavItems" :key="item.path" :to="item.path" :class="{ active: route.path === item.path }"><el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span></RouterLink></nav>
  </div>
</template>

<style>
* { box-sizing: border-box; }
html, body, #app { min-height: 100%; margin: 0; }
body { background: var(--mf-page-bg); color: var(--mf-text); font-family: Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif; }
:root { --mf-page-bg: #f7f8fa; --mf-shell-bg: radial-gradient(circle at 15% 0%, #eee8ff 0, transparent 24%), #f7f8fa; --mf-surface: rgb(255 255 255 / 94%); --mf-surface-muted: #fafbfc; --mf-border: #eff0f4; --mf-text: #20293a; --mf-text-muted: #687282; --mf-nav-hover: #f1ecff; }
html.dark { --mf-page-bg: #151822; --mf-shell-bg: radial-gradient(circle at 15% 0%, #302550 0, transparent 28%), #151822; --mf-surface: rgb(31 35 48 / 94%); --mf-surface-muted: #252a37; --mf-border: #393f50; --mf-text: #f0f2f7; --mf-text-muted: #b2bac8; --mf-nav-hover: #353047; }
.app-shell { min-height: 100vh; padding: 12px; background: var(--mf-shell-bg); transition: background .2s; }
.topbar { display: flex; min-height: 76px; align-items: center; gap: 24px; padding: 0 16px; border: 1px solid var(--mf-border); border-radius: 22px; background: var(--mf-surface); box-shadow: 0 12px 30px rgb(64 66 90 / 7%); }
.brand { display: flex; flex: 0 0 auto; align-items: center; gap: 10px; color: var(--mf-text); font-size: 18px; font-weight: 800; text-decoration: none; letter-spacing: -.5px; }
.brand-mark { width: 48px; height: 48px; flex: 0 0 48px; filter: drop-shadow(0 8px 18px rgb(146 112 244 / 28%)); }
.brand small { padding: 6px 11px; border: 1px solid var(--mf-border); border-radius: 999px; color: var(--mf-text-muted); font-size: 12px; font-weight: 700; letter-spacing: 0; }
.main-nav { display: flex; gap: 2px; align-items: center; margin: 0 auto; padding: 5px; border: 1px solid var(--mf-border); border-radius: 17px; background: var(--mf-surface-muted); }
.main-nav a { display: grid; min-height: 43px; padding: 0 16px; place-items: center; border-radius: 11px; color: var(--mf-text-muted); font-size: 14px; font-weight: 700; text-decoration: none; white-space: nowrap; transition: color .2s, background .2s, box-shadow .2s; }
.main-nav a:hover { background: var(--mf-nav-hover); color: #aa86fb; }.main-nav a.active { background: #aa86fb; color: #fff; box-shadow: 0 5px 12px rgb(151 112 239 / 28%); }
.top-actions { display: flex; gap: 7px; align-items: center; }.top-actions .el-button { color: var(--mf-text-muted); font-size: 20px; }.theme-menu .el-dropdown-menu__item { gap: 8px; }.theme-menu .el-dropdown-menu__item.active { color: var(--el-color-primary); font-weight: 700; }.service-avatar { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 50%; background: #2e3749; color: #c4b1ff; font-size: 17px; }
.app-main { max-width: 1784px; margin: 0 auto; padding: 22px 0 44px; }.mobile-nav { display: none; }
html.dark .page-header, html.dark .hero { background: linear-gradient(120deg, #252a38 40%, #30284a) !important; border-color: #494056 !important; }
html.dark :is(.shell, .welcome-card, .stat-card, .panel, .watch-summary, .watch-workspace, .profile-workspace, .profile-list-panel, .system-card, .list, .browser-entry, .rule-card) { background: #202532 !important; border-color: #3a4152 !important; }
html.dark :is(.tabs, .overview, .detail-card, .watch-inspector, .editor-form section, .queue-summary, .summary i, .browser-toolbar .el-input__wrapper) { background: #282e3c !important; border-color: #3d4557 !important; }
html.dark :is(.page-header, .hero, .shell, .welcome-card, .stat-card, .panel, .watch-summary, .watch-workspace, .profile-workspace, .profile-list-panel, .system-card, .list, .detail-card, .watch-inspector, .editor-form section, .rule-card, .browser-entry) :is(h1, h2, h3, strong, dd, .heading, .folder-heading) { color: #eef1f7; }
html.dark :is(.page-header, .hero, .shell, .welcome-card, .stat-card, .panel, .watch-summary, .watch-workspace, .profile-workspace, .profile-list-panel, .system-card, .list, .detail-card, .watch-inspector, .editor-form section, .rule-card, .browser-entry) :is(p, span, small, code, dt) { color: #b5bece; }
html.dark :is(.row, .task-row, .monitor-rows div, .overview > div, .tool, .table-toolbar, .inspector-section, .watch-summary > div, .profile-list-item, .watch-list-item) { border-color: #3a4152 !important; }
html.dark :is(.profile-list-item, .watch-list-item, .browser-entry) { background: #252b39 !important; color: #e5e9f0; }
html.dark .mobile-nav { background: rgb(31 35 48 / 96%); }.app-main { color: var(--mf-text); }
html.dark .toolbar-controls .el-button, html.dark .toolbar-controls .el-select__wrapper, html.dark .toolbar-controls .el-input__wrapper { color: #d8deea !important; background: #262c3a !important; border-color: #41495b !important; box-shadow: 0 0 0 1px #41495b inset !important; }
html.dark .workbench-actions .el-button { color: #b9c3d3 !important; background: #262c3a !important; border-color: #41495b !important; }
html.dark .folder-panel .el-tree-node__content:hover, html.dark .folder-panel .is-current > .el-tree-node__content { background: #302c44 !important; }
html.dark .library-source:hover { background: #302c44 !important; }
html.dark :is(.profile-row-actions, .watch-row-actions) .el-button.is-link { color: #c6d0df !important; }
html.dark :is(.profile-row-actions, .watch-row-actions) .el-button--primary.is-link { color: #84baff !important; }
html.dark :is(.profile-row-actions, .watch-row-actions) .el-button--danger.is-link { color: #ff8e9b !important; }
html.dark .watch-row-actions .el-button--warning.is-link { color: #f4c66f !important; }
html.dark .watch-row-actions .el-button--success.is-link { color: #72dca9 !important; }
html.dark :is(.profile-row-actions, .watch-row-actions) .el-button.is-link:hover { color: #d8c2ff !important; }
html.dark :is(.profile-row-actions, .watch-row-actions) .el-button.is-link > span { color: inherit !important; }
html.dark .detail-summary, html.dark .conversion-files-panel, html.dark .delivery-rule-card, html.dark .delivery-preview, html.dark .naming-preview { background: #252b39 !important; border-color: #41495b !important; }
html.dark .conversion-files-panel, html.dark .conversion-panel-heading, html.dark .conversion-file-row, html.dark .selection-summary, html.dark .settings-heading, html.dark .output-estimate { border-color: #41495b !important; }
html.dark :is(.detail-summary, .conversion-files-panel, .delivery-rule-card, .delivery-preview, .naming-preview) :is(strong, .delivery-rule-head) { color: #eef1f7 !important; }
html.dark :is(.detail-summary, .conversion-files-panel, .delivery-rule-card, .delivery-preview, .naming-preview) :is(span, small, code) { color: #b5bece !important; }
html.dark .conversion-files-panel .conversion-cover, html.dark .detail-summary .detail-cover { background: #353047 !important; }
@media (max-width: 1080px) { .topbar { gap: 13px; }.main-nav { max-width: calc(100vw - 280px); overflow-x: auto; }.main-nav a { padding: 0 12px; } }
@media (max-width: 700px) { .app-shell { padding: 0 0 82px; }.topbar { min-height: 64px; gap: 0; border-width: 0 0 1px; border-radius: 0; padding: 10px 14px; }.brand-mark { width: 38px; height: 38px; border-radius: 11px; font-size: 17px; }.brand { font-size: 17px; }.brand small, .main-nav { display: none; }.top-actions { margin-left: auto; }.service-avatar { display: none; }.app-main { padding: 14px 12px 20px; }.mobile-nav { position: fixed; z-index: 20; right: 0; bottom: 0; left: 0; display: grid; grid-template-columns: repeat(6, 1fr); min-height: 66px; padding: 7px max(8px, env(safe-area-inset-right)) calc(7px + env(safe-area-inset-bottom)) max(8px, env(safe-area-inset-left)); background: var(--mf-surface); box-shadow: 0 -8px 24px rgb(40 48 70 / 5%); backdrop-filter: blur(14px); }.mobile-nav a { display: flex; flex-direction: column; gap: 3px; align-items: center; justify-content: center; color: var(--mf-text-muted); font-size: 9px; font-weight: 650; text-decoration: none; }.mobile-nav .el-icon { font-size: 18px; }.mobile-nav a.active { color: #b693ff; }.mobile-nav a.active .el-icon { display: grid; width: 29px; height: 26px; place-items: center; border-radius: 10px; color: #fff; background: #a881f3; box-shadow: 0 5px 12px rgb(157 112 239 / 25%); } }
</style>
