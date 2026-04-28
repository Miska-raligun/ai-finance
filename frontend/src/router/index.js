import { createRouter, createWebHistory } from 'vue-router'

// 仅登录页同步加载（首屏路径），其余视图按需异步加载，
// 让 ECharts / Chart.js 等重型依赖只在进入对应页面时下载。
import LoginView from '../views/LoginView.vue'

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: LoginView },
  { path: '/chat', name: 'ChatView', component: () => import('../views/ChatView.vue') },
  { path: '/ledger', component: () => import('../views/LedgerView.vue') },
  { path: '/investment', component: () => import('../views/InvestmentView.vue') },
  { path: '/reports', component: () => import('../views/ReportsView.vue') },
  { path: '/admin', component: () => import('../views/AdminView.vue') }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
