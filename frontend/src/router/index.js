import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import LedgerView from '../views/LedgerView.vue'
import LoginView from '../views/LoginView.vue'

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: LoginView },
  { path: '/chat', name: 'ChatView', component: ChatView },
  { path: '/ledger', component: LedgerView }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
