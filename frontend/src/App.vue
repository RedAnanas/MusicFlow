<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <el-container class="app-container">
    <!-- 侧边栏 -->
    <el-aside width="220px" class="app-aside">
      <div class="logo">
        <h2>🎵 MusicFlow</h2>
        <p>NAS 音乐转换与整理工具</p>
      </div>
      <el-menu
        default-active="/"
        router
        class="aside-menu"
      >
        <el-menu-item index="/">
          <el-icon><Monitor /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/files">
          <el-icon><Document /></el-icon>
          <span>音乐文件</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><List /></el-icon>
          <span>转换任务</span>
        </el-menu-item>
        <el-menu-item index="/profiles">
          <el-icon><Setting /></el-icon>
          <span>转换配置</span>
        </el-menu-item>
        <el-menu-item index="/watch-folders">
          <el-icon><FolderOpened /></el-icon>
          <span>监控目录</span>
        </el-menu-item>
        <el-menu-item index="/logs">
          <el-icon><Tickets /></el-icon>
          <span>日志</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-container class="main-container">
      <el-header class="app-header">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
        </el-breadcrumb>
      </el-header>

      <el-main class="app-main">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  height: 100%;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', Arial, sans-serif;
}

#app {
  height: 100%;
}

.app-container {
  height: 100vh;
}

.app-aside {
  background-color: #001529;
  color: #fff;
}

.logo {
  padding: 20px;
  text-align: center;
  border-bottom: 1px solid #0d2137;
}

.logo h2 {
  font-size: 18px;
  margin-bottom: 5px;
}

.logo p {
  font-size: 12px;
  color: #889aa4;
}

.aside-menu {
  border: none;
  background-color: #001529;
}

.aside-menu .el-menu-item {
  color: #889aa4 !important;
  background-color: transparent !important;
}

.aside-menu .el-menu-item:hover {
  background-color: #0d2137 !important;
  color: #fff !important;
}

.aside-menu .el-menu-item.is-active {
  color: #409eff !important;
  background-color: #0d2137 !important;
}

.aside-menu .el-menu-item:focus {
  background-color: transparent !important;
  color: #889aa4 !important;
}

.aside-menu .el-menu-item:active {
  background-color: #0d2137 !important;
}

.main-container {
  flex-direction: column;
}

.app-header {
  background-color: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  padding: 0 20px;
}

.app-main {
  background-color: #f5f7fa;
  padding: 20px;
}
</style>
