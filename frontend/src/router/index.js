import { createRouter, createWebHistory } from 'vue-router'

// 入口三件套(Login + Home + Chat)同步引入,登录后立刻可交互;它们均不静态依赖
// ECharts / Chart.js,主 bundle 里不会被这些大库绑住。
import ChatView from '../views/ChatView.vue'
import LoginView from '../views/LoginView.vue'
import HomeView from '../views/HomeView.vue'

// 含 ECharts 的视图全部异步:LedgerView 通过 ChartPanel/SpendCalendar/IncomeSankey
// 间接吃下 vendor-echarts,如果同步加载会让主 bundle 在登录页就拽下 gzip 233 KB
// 的图表库。改成动态 import 后,这些 chunk 只在用户真正进 /ledger 等页面时才下载。
const LedgerView = () => import('../views/LedgerView.vue')
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
