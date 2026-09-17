<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Document, Files, FolderOpened, House, Setting } from '@element-plus/icons-vue'

const route = useRoute()
const appVersion = __MUSICFLOW_VERSION__
const navItems = [
  { path: '/', label: '首页', icon: House },
  { path: '/files', label: '操作台', icon: Files },
  { path: '/tasks', label: '操作记录', icon: Document },
  { path: '/profiles', label: '转换方案', icon: Document },
  { path: '/watch-folders', label: '监控目录', icon: FolderOpened },
  { path: '/logs', label: '运行日志', icon: Document },
  { path: '/system', label: '系统设置', icon: Setting },
]
const mobileNavItems = navItems.filter(item => ['/', '/files', '/tasks', '/watch-folders', '/system'].includes(item.path))
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink to="/" class="brand" aria-label="MusicFlow 首页"><span class="brand-mark">M</span><span>MusicFlow</span><small>v{{ appVersion }}</small></RouterLink>
      <nav class="main-nav" aria-label="主导航"><RouterLink v-for="item in navItems" :key="item.path" :to="item.path" :class="{ active: route.path === item.path }">{{ item.label }}</RouterLink></nav>
      <div class="top-actions"><el-button text circle aria-label="搜索"><el-icon><Search /></el-icon></el-button><el-button text circle aria-label="通知"><el-icon><Bell /></el-icon></el-button><span class="service-avatar" title="本地服务"><el-icon><Connection /></el-icon></span></div>
    </header>
    <main class="app-main"><RouterView /></main>
    <nav class="mobile-nav" aria-label="移动端主导航"><RouterLink v-for="item in mobileNavItems" :key="item.path" :to="item.path" :class="{ active: route.path === item.path }"><el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span></RouterLink></nav>
  </div>
</template>

<style>
* { box-sizing: border-box; } html, body, #app { min-height: 100%; margin: 0; } body { background: #f7f8fa; color: #20293a; font-family: Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif; }
.app-shell { min-height: 100vh; padding: 12px; background: radial-gradient(circle at 15% 0%, #eee8ff 0, transparent 24%), #f7f8fa; }.topbar { display: flex; min-height: 76px; align-items: center; gap: 24px; padding: 0 16px; border: 1px solid #eff0f4; border-radius: 22px; background: rgb(255 255 255 / 94%); box-shadow: 0 12px 30px rgb(64 66 90 / 7%); }.brand { display: flex; flex: 0 0 auto; align-items: center; gap: 10px; color: #20293a; font-size: 18px; font-weight: 800; text-decoration: none; letter-spacing: -.5px; }.brand-mark { display: grid; width: 48px; height: 48px; place-items: center; border-radius: 13px; background: linear-gradient(135deg, #bb9cff, #8f6df1); color: #fff; font-size: 20px; box-shadow: 0 8px 18px rgb(146 112 244 / 28%); }.brand small { padding: 6px 11px; border: 1px solid #e8e9ee; border-radius: 999px; color: #606978; font-size: 12px; font-weight: 700; letter-spacing: 0; }.main-nav { display: flex; gap: 2px; align-items: center; margin: 0 auto; padding: 5px; border: 1px solid #eff0f4; border-radius: 17px; background: #fafbfc; }.main-nav a { display: grid; min-height: 43px; padding: 0 16px; place-items: center; border-radius: 11px; color: #687282; font-size: 14px; font-weight: 700; text-decoration: none; white-space: nowrap; transition: color .2s, background .2s, box-shadow .2s; }.main-nav a:hover { background: #f1ecff; color: #7254d2; }.main-nav a.active { background: #aa86fb; color: #fff; box-shadow: 0 5px 12px rgb(151 112 239 / 28%); }.top-actions { display: flex; gap: 7px; align-items: center; }.top-actions .el-button { color: #657080; font-size: 20px; }.service-avatar { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 50%; background: #2e3749; color: #c4b1ff; font-size: 17px; }
.app-main { max-width: 1784px; margin: 0 auto; padding: 22px 0 44px; }.mobile-nav { display: none; } @media (max-width: 1080px) { .topbar { gap: 13px; }.main-nav { max-width: calc(100vw - 280px); overflow-x: auto; }.main-nav a { padding: 0 12px; } } @media (max-width: 700px) { .app-shell { padding: 0 0 82px; }.topbar { min-height: 64px; gap: 0; border-width: 0 0 1px; border-radius: 0; padding: 10px 14px; }.brand-mark { width: 38px; height: 38px; border-radius: 11px; font-size: 17px; }.brand { font-size: 17px; }.brand small, .main-nav { display: none; }.top-actions { margin-left: auto; }.service-avatar { display: none; }.app-main { padding: 14px 12px 20px; }.mobile-nav { position: fixed; z-index: 20; right: 0; bottom: 0; left: 0; display: grid; grid-template-columns: repeat(5, 1fr); min-height: 66px; padding: 7px max(12px, env(safe-area-inset-right)) calc(7px + env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left)); background: rgb(255 255 255 / 96%); box-shadow: 0 -8px 24px rgb(40 48 70 / 5%); backdrop-filter: blur(14px); }.mobile-nav a { display: flex; flex-direction: column; gap: 3px; align-items: center; justify-content: center; color: #8791a1; font-size: 10px; font-weight: 650; text-decoration: none; }.mobile-nav .el-icon { font-size: 19px; }.mobile-nav a.active { color: #9a72ed; }.mobile-nav a.active .el-icon { display: grid; width: 31px; height: 27px; place-items: center; border-radius: 10px; color: #fff; background: #a881f3; box-shadow: 0 5px 12px rgb(157 112 239 / 25%); } }
</style>
