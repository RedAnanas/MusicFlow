<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
const appVersion = __MUSICFLOW_VERSION__
const navItems = [
  { path: '/', label: '首页' },
  { path: '/files', label: '操作台' },
  { path: '/tasks', label: '操作记录' },
  { path: '/profiles', label: '转换方案' },
  { path: '/watch-folders', label: '监控目录' },
  { path: '/logs', label: '运行日志' },
  { path: '/system', label: '系统设置' },
]
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink to="/" class="brand" aria-label="MusicFlow 首页"><span class="brand-mark">M</span><span>MusicFlow</span><small>v{{ appVersion }}</small></RouterLink>
      <nav class="main-nav" aria-label="主导航"><RouterLink v-for="item in navItems" :key="item.path" :to="item.path" :class="{ active: route.path === item.path }">{{ item.label }}</RouterLink></nav>
      <div class="top-actions"><el-button text circle aria-label="搜索"><el-icon><Search /></el-icon></el-button><el-button text circle aria-label="通知"><el-icon><Bell /></el-icon></el-button><span class="service-avatar" title="本地服务"><el-icon><Connection /></el-icon></span></div>
    </header>
    <main class="app-main"><RouterView /></main>
  </div>
</template>

<style>
* { box-sizing: border-box; } html, body, #app { min-height: 100%; margin: 0; } body { background: #f7f8fa; color: #20293a; font-family: Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif; }
.app-shell { min-height: 100vh; padding: 12px; background: radial-gradient(circle at 15% 0%, #eee8ff 0, transparent 24%), #f7f8fa; }.topbar { display: flex; min-height: 76px; align-items: center; gap: 24px; padding: 0 16px; border: 1px solid #eff0f4; border-radius: 22px; background: rgb(255 255 255 / 94%); box-shadow: 0 12px 30px rgb(64 66 90 / 7%); }.brand { display: flex; flex: 0 0 auto; align-items: center; gap: 10px; color: #20293a; font-size: 18px; font-weight: 800; text-decoration: none; letter-spacing: -.5px; }.brand-mark { display: grid; width: 48px; height: 48px; place-items: center; border-radius: 13px; background: linear-gradient(135deg, #bb9cff, #8f6df1); color: #fff; font-size: 20px; box-shadow: 0 8px 18px rgb(146 112 244 / 28%); }.brand small { padding: 6px 11px; border: 1px solid #e8e9ee; border-radius: 999px; color: #606978; font-size: 12px; font-weight: 700; letter-spacing: 0; }.main-nav { display: flex; gap: 2px; align-items: center; margin: 0 auto; padding: 5px; border: 1px solid #eff0f4; border-radius: 17px; background: #fafbfc; }.main-nav a { display: grid; min-height: 43px; padding: 0 16px; place-items: center; border-radius: 11px; color: #687282; font-size: 14px; font-weight: 700; text-decoration: none; white-space: nowrap; transition: color .2s, background .2s, box-shadow .2s; }.main-nav a:hover { background: #f1ecff; color: #7254d2; }.main-nav a.active { background: #aa86fb; color: #fff; box-shadow: 0 5px 12px rgb(151 112 239 / 28%); }.top-actions { display: flex; gap: 7px; align-items: center; }.top-actions .el-button { color: #657080; font-size: 20px; }.service-avatar { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 50%; background: #2e3749; color: #c4b1ff; font-size: 17px; }
.app-main { max-width: 1784px; margin: 0 auto; padding: 22px 0 44px; } @media (max-width: 1080px) { .topbar { gap: 13px; }.main-nav { max-width: calc(100vw - 280px); overflow-x: auto; }.main-nav a { padding: 0 12px; } } @media (max-width: 700px) { .app-shell { padding: 0 0 16px; }.topbar { min-height: 110px; flex-wrap: wrap; gap: 0; border-width: 0 0 1px; border-radius: 0; padding: 10px 14px 0; }.brand-mark { width: 38px; height: 38px; border-radius: 11px; font-size: 17px; }.brand { font-size: 17px; }.brand small { display: none; }.top-actions { margin-left: auto; }.service-avatar { display: none; }.main-nav { order: 3; width: 100%; max-width: none; height: 48px; margin: 5px 0 0; border: 0; border-radius: 0; padding: 3px 0; background: transparent; }.main-nav a { min-height: 38px; padding: 0 12px; font-size: 13px; }.app-main { padding: 14px 12px 32px; } }
</style>
