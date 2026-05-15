import { createRouter, createWebHistory } from 'vue-router'

// 全部同步 import：每个 view 体积都 ≤ 50KB，合并到主 bundle 后切换路由是
// 纯前端跳转，零网络往返。早期改成 dynamic import 是为了首屏小，但实际
// 收益小（vendor-element-plus 已经吃掉 800KB+），却让用户感知每次切页都
// "卡"——首次进每个新页要等 chunk 文件。
import ChatView from '../views/ChatView.vue'
import LedgerView from '../views/LedgerView.vue'
import LoginView from '../views/LoginView.vue'
import AdminView from '../views/AdminView.vue'
import InvestmentView from '../views/InvestmentView.vue'
import ReportsView from '../views/ReportsView.vue'
import HomeView from '../views/HomeView.vue'

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
