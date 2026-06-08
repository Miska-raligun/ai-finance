import { createRouter, createWebHistory } from 'vue-router'

// 首屏 / 高频路由同步引入，进入零网络往返：
//   Login / Home / Chat / Ledger 都不挂大图表库，留主 bundle。
import ChatView from '../views/ChatView.vue'
import LedgerView from '../views/LedgerView.vue'
import LoginView from '../views/LoginView.vue'
import HomeView from '../views/HomeView.vue'

// 重图表/低频路由改为异步组件，把 ECharts / Chart.js 推迟到真正进入这些页面才拉。
// 这样首屏不再被 vendor-echarts (gzip 232 KB) + vendor-chartjs (gzip 70 KB) 拖累。
const InvestmentView = () => import('../views/InvestmentView.vue')
const ReportsView = () => import('../views/ReportsView.vue')
const AdminView = () => import('../views/AdminView.vue')

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: LoginView },
  { path: '/home', name: 'HomeView', component: HomeView },
  { path: '/chat', name: 'ChatView', component: ChatView },
  { path: '/ledger', component: LedgerView },
  { path: '/investment', component: InvestmentView },
  { path: '/reports', component: ReportsView },
  { path: '/admin', component: AdminView }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
