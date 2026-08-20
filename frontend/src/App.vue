<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

const route = useRoute()
const pageTitle = computed(() => ({ '/': '仪表盘', '/files': '音乐库', '/tasks': '转换任务', '/profiles': '转换方案', '/watch-folders': '监控目录', '/logs': '日志' }[route.path] || 'MusicFlow'))
</script>

<template>
  <el-container class="app-container">
    <el-aside width="244px" class="app-aside">
      <div class="logo"><div class="logo-mark"><el-icon><Headset /></el-icon></div><div><h1>MusicFlow</h1><p>NAS 音乐转换与整理工具</p></div></div>
      <el-menu :default-active="$route.path" router class="aside-menu">
        <el-menu-item index="/"><el-icon><Monitor /></el-icon><span>控制台</span></el-menu-item>
        <el-menu-item index="/files"><el-icon><Document /></el-icon><span>音乐库</span></el-menu-item>
        <el-menu-item index="/tasks"><el-icon><List /></el-icon><span>转换任务</span></el-menu-item>
        <el-menu-item index="/profiles"><el-icon><Setting /></el-icon><span>转换方案</span></el-menu-item>
        <el-menu-item index="/watch-folders"><el-icon><FolderOpened /></el-icon><span>监控目录</span></el-menu-item>
        <el-menu-item index="/logs"><el-icon><Tickets /></el-icon><span>日志</span></el-menu-item>
      </el-menu>
      <div class="aside-footer"><div class="storage-title"><span>NAS 存储</span><span>52%</span></div><el-progress :percentage="52" :show-text="false" :stroke-width="6" /><p>4.21 TB / 8 TB</p><div class="collapse-hint"><el-icon><DArrowLeft /></el-icon>收起导航</div></div>
    </el-aside>
    <el-container class="main-container">
      <el-header class="app-header"><div class="header-status"><el-icon><Coin /></el-icon><span>NAS 已连接</span></div><div class="header-divider"></div><div class="header-title">{{ pageTitle }}</div><div class="header-actions"><el-button text circle aria-label="帮助"><el-icon><QuestionFilled /></el-icon></el-button><el-button text circle aria-label="通知"><el-icon><Bell /></el-icon></el-button><el-avatar :size="32">M</el-avatar><span class="user-name">musicfan</span><el-icon><ArrowDown /></el-icon></div></el-header>
      <el-main class="app-main"><RouterView /></el-main>
    </el-container>
  </el-container>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; font-family: Inter, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', Arial, sans-serif; }
#app, .app-container { height: 100%; }
:root { --mf-green: #0c9c68; --mf-green-dark: #06251e; --mf-green-soft: #e5f5ed; --mf-ink: #1f2d26; --mf-muted: #748179; --mf-line: #dfe4df; --mf-surface: #fffefa; }
.app-aside { position: relative; display: flex; flex-direction: column; background: #06251e; color: #fff; }
.logo { display: flex; align-items: center; gap: 10px; padding: 28px 24px 24px; }.logo-mark { display: grid; width: 32px; height: 32px; place-items: center; border-radius: 10px; background: #13bf7a; color: #06251e; font-size: 19px; }.logo h1 { margin: 0 0 3px; color: #f1fff8; font-size: 21px; letter-spacing: -.6px; }.logo p { color: #88aa9b; font-size: 11px; }
.aside-menu { flex: 1; padding: 4px 12px; border: none; background: transparent; }.aside-menu .el-menu-item { height: 48px; margin: 3px 0; border-radius: 8px; color: #9ebbae !important; background: transparent !important; }.aside-menu .el-menu-item:hover, .aside-menu .el-menu-item:active, .aside-menu .el-menu-item.is-active { background: #103c31 !important; }.aside-menu .el-menu-item:hover { color: #fff !important; }.aside-menu .el-menu-item.is-active { color: #56e0a6 !important; }
.aside-footer { padding: 20px 24px 22px; color: #8da99c; font-size: 12px; }.storage-title { display: flex; justify-content: space-between; margin-bottom: 9px; color: #d7eadf; }.aside-footer .el-progress-bar__outer { background: #164339; }.aside-footer .el-progress-bar__inner { background: #16c784; }.aside-footer p { margin: 9px 0 24px; }.collapse-hint { display: flex; gap: 8px; align-items: center; padding-top: 18px; border-top: 1px solid #164339; }
.main-container { flex-direction: column; }.app-header { display: flex; gap: 16px; align-items: center; height: 76px; padding: 0 40px; background: #fffefa; border-bottom: 1px solid #e7e9e4; }.app-main { padding: 0 40px 44px; background: #f8f9f5; }.header-status { display: flex; gap: 8px; align-items: center; color: #25332d; font-size: 14px; }.header-status .el-icon { color: #179365; }.header-divider { width: 1px; height: 20px; background: #dde2dd; }.header-title { color: #718078; font-size: 14px; }.header-actions { display: flex; gap: 12px; align-items: center; margin-left: auto; color: #314039; font-size: 14px; }.header-actions .el-button { color: #536158; }.header-actions .el-avatar { background: #13a96f; color: #fff; font-size: 13px; }.user-name { margin-left: -5px; }
.product-page { max-width: 1320px; margin: 0 auto; padding-top: 34px; }.product-page .page-header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; margin-bottom: 24px; }.product-page .page-title-block h1 { margin: 0 0 8px; color: var(--mf-ink); font-size: 32px; line-height: 1.2; letter-spacing: -.8px; }.product-page .page-title-block p { color: var(--mf-muted); font-size: 14px; line-height: 1.6; }.product-page > .el-card { border: 1px solid var(--mf-line); border-radius: 12px; background: var(--mf-surface); box-shadow: none; }.product-page > .el-card > .el-card__body { padding: 0; }.product-page .el-button--primary { border-color: var(--mf-green); background: var(--mf-green); }.product-page .el-button--primary.is-link, .product-page .el-button--primary.is-text { border-color: transparent; background: transparent; color: var(--mf-green); }.product-page .el-table { --el-table-border-color: #e7ebe7; --el-table-header-bg-color: #f4f7f3; --el-table-row-hover-bg-color: #f2f8f4; color: #425048; }.product-page .el-table th.el-table__cell { height: 46px; color: #748179; font-size: 12px; font-weight: 600; }.product-page .el-table td.el-table__cell { height: 58px; }.product-page .el-tag { border-radius: 999px; }.product-page .el-input__wrapper, .product-page .el-select__wrapper { border-radius: 8px; box-shadow: 0 0 0 1px #ced7d0 inset; }.product-page .el-input__wrapper.is-focus, .product-page .el-select__wrapper.is-focused { box-shadow: 0 0 0 1px var(--mf-green) inset !important; }.product-page .el-pagination { padding: 18px 20px; }
@media (max-width: 900px) { .app-aside { width: 72px !important; }.logo { justify-content: center; padding: 22px 12px; }.logo > div:last-child, .aside-menu span, .aside-footer, .header-title, .user-name, .header-divider { display: none; }.aside-menu { padding: 4px 8px; }.aside-menu .el-menu-item { justify-content: center; padding: 0 !important; }.app-header, .app-main { padding-left: 24px; padding-right: 24px; } }
@media (max-width: 720px) { .product-page { padding-top: 24px; }.product-page .page-header { align-items: stretch; flex-direction: column; }.product-page .page-header > .el-button { width: 100%; }.product-page .page-title-block h1 { font-size: 28px; } }
</style>
