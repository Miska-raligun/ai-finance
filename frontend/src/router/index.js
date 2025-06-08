import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import LedgerView from '../views/LedgerView.vue'

const routes = [
  { path: '/', redirect: '/chat' },
  { path: '/chat', name: 'ChatView',component: ChatView },
  { path: '/ledger', component: LedgerView }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
