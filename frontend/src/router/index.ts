import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
  },
  {
    path: '/files',
    name: 'Files',
    component: () => import('../views/Files.vue'),
  },
  {
    path: '/tasks',
    name: 'Tasks',
    component: () => import('../views/Tasks.vue'),
  },
  {
    path: '/profiles',
    name: 'Profiles',
    component: () => import('../views/Profiles.vue'),
  },
  {
    path: '/watch-folders',
    name: 'WatchFolders',
    component: () => import('../views/WatchFolders.vue'),
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('../views/Logs.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
