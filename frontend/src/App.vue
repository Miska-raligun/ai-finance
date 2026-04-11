<!-- src/App.vue -->
<template>
  <el-container style="height: 100vh; height: 100dvh">
    <!-- PC 侧边栏 -->
    <el-aside v-if="!isMobile && route.path !== '/login'" width="220px" class="app-aside">
      <div class="brand">
        <span class="brand-icon">💰</span>
        <span class="brand-name">智能记账</span>
      </div>
      <nav class="side-nav">
        <router-link to="/chat" class="nav-item" :class="{ active: route.path === '/chat' }">
          <span class="nav-icon">💬</span> 聊天记账
        </router-link>
        <router-link to="/ledger" class="nav-item" :class="{ active: route.path === '/ledger' }">
          <span class="nav-icon">📒</span> 账本管理
        </router-link>
        <router-link v-if="isAdmin" to="/admin" class="nav-item" :class="{ active: route.path === '/admin' }">
          <span class="nav-icon">🛠</span> 用户管理
        </router-link>
      </nav>
      <div class="side-footer">
        <div class="user-info">
          <div class="user-avatar">{{ username.slice(0, 1).toUpperCase() }}</div>
          <div class="user-name">{{ username }}</div>
        </div>
        <div class="side-actions">
          <button class="side-btn" @click="openConfigPanel">⚙️ 模型配置</button>
          <button class="side-btn danger" @click="logout">🚪 退出登录</button>
        </div>
      </div>
    </el-aside>

    <!-- 移动端侧边抽屉 -->
    <el-drawer
      v-if="isMobile && route.path !== '/login'"
      v-model="showDrawer"
      :with-header="false"
      size="240px"
      class="mobile-drawer"
      direction="ltr"
    >
      <div class="app-aside drawer-inner">
        <div class="brand">
          <span class="brand-icon">💰</span>
          <span class="brand-name">智能记账</span>
        </div>
        <nav class="side-nav">
          <router-link to="/chat" class="nav-item" :class="{ active: route.path === '/chat' }" @click="showDrawer=false">
            <span class="nav-icon">💬</span> 聊天记账
          </router-link>
          <router-link to="/ledger" class="nav-item" :class="{ active: route.path === '/ledger' }" @click="showDrawer=false">
            <span class="nav-icon">📒</span> 账本管理
          </router-link>
          <router-link v-if="isAdmin" to="/admin" class="nav-item" :class="{ active: route.path === '/admin' }" @click="showDrawer=false">
            <span class="nav-icon">🛠</span> 用户管理
          </router-link>
        </nav>
        <div class="side-footer">
          <div class="user-info">
            <div class="user-avatar">{{ username.slice(0, 1).toUpperCase() }}</div>
            <div class="user-name">{{ username }}</div>
          </div>
          <div class="side-actions">
            <button class="side-btn" @click="openConfigPanel(); showDrawer=false">⚙️ 模型配置</button>
            <button class="side-btn danger" @click="logout">🚪 退出登录</button>
          </div>
        </div>
      </div>
    </el-drawer>

    <el-container style="flex-direction: column; overflow: hidden; min-width: 0;">
      <!-- 移动端顶部导航栏 -->
      <header v-if="isMobile && route.path !== '/login'" class="mobile-topbar">
        <button class="topbar-menu-btn" @click="showDrawer = true">☰</button>
        <span class="topbar-title">
          {{ route.path === '/chat' ? '聊天记账' : route.path === '/ledger' ? '账本管理' : '用户管理' }}
        </span>
        <div class="topbar-user">{{ username.slice(0, 1).toUpperCase() }}</div>
      </header>

      <el-main :class="{ 'has-topbar': isMobile && route.path !== '/login' }">
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>

        <!-- LLM 配置弹窗 -->
        <el-dialog v-model="showConfig" title="⚙ LLM 配置" width="420px">
          <el-form label-width="90px" autocomplete="off">
            <el-form-item label="API URL">
              <el-input v-model="llmUrl" placeholder="https://api.example.com" autocomplete="off" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="llmKey" type="password" show-password autocomplete="new-password" />
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input v-model="llmModel" placeholder="Pro/deepseek-ai/DeepSeek-V3" autocomplete="off" />
            </el-form-item>
            <el-form-item label="角色人设">
              <el-input v-model="llmPersona" type="textarea" :rows="2" placeholder="一个有点傲娇的财务顾问" autocomplete="off" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="useDefault">加载系统默认</el-button>
            <el-button type="primary" @click="saveConfig">保存配置</el-button>
          </template>
        </el-dialog>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { ref, computed, watchEffect, onMounted, watch, onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const { isAdmin } = storeToRefs(userStore)

const username = computed(() => userStore.username)

const active = ref(route.path)
const showConfig = ref(false)
const llmUrl = ref('')
const llmKey = ref('')
const llmModel = ref('')
const llmPersona = ref('')
const isMobile = ref(window.innerWidth < 768)
const showDrawer = ref(false)

function updateIsMobile() {
  isMobile.value = window.innerWidth < 768
}
onMounted(() => {
  updateIsMobile()
  window.addEventListener('resize', updateIsMobile)
})
onBeforeUnmount(() => window.removeEventListener('resize', updateIsMobile))

watchEffect(() => { active.value = route.path })

onMounted(() => userStore.fetchMe())
watch(() => route.path, () => userStore.fetchMe())

function checkConfig() {
  if (route.path !== '/login' && userStore.needLlmConfig()) {
    showConfig.value = true
  }
}
onMounted(checkConfig)
watch(() => route.path, checkConfig)

async function saveConfig() {
  await userStore.saveLlmConfig({
    url: llmUrl.value,
    apikey: llmKey.value,
    model: llmModel.value,
    persona: llmPersona.value,
  })
  showConfig.value = false
}
async function useDefault() {
  await userStore.useDefaultLlm()
  showConfig.value = false
}
async function logout() {
  await userStore.logout()
  router.push('/login')
}
function openConfigPanel() {
  showConfig.value = true
}
</script>

<style>
/* ===== 全局 CSS 变量 ===== */
:root {
  --color-primary: #2563EB;
  --color-primary-dark: #1D4ED8;
  --color-primary-light: #DBEAFE;
  --color-bg: #EFF6FF;
  --color-surface: #FFFFFF;
  --color-text: #1e3a5f;
  --color-text-muted: #4a7aad;
  --color-border: #BFDBFE;
  --shadow-card: 0 1px 3px rgba(37,99,235,0.08), 0 4px 16px rgba(37,99,235,0.08);
  --radius-card: 12px;
  --topbar-height: 56px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Helvetica Neue', Arial, sans-serif;
  background: var(--color-bg);
  color: var(--color-text);
  -webkit-font-smoothing: antialiased;
}

/* ===== 全局 Element Plus 覆盖 ===== */
.el-card {
  border-radius: var(--radius-card) !important;
  border: 1px solid var(--color-border) !important;
  box-shadow: var(--shadow-card) !important;
  background: var(--color-surface) !important;
}
.el-card__header {
  font-weight: 600;
  font-size: 15px;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border) !important;
  padding: 14px 18px !important;
}
.el-card__body {
  padding: 18px !important;
}
.el-button--primary {
  background: var(--color-primary) !important;
  border-color: var(--color-primary) !important;
}
.el-button--primary:hover,
.el-button--primary:focus {
  background: var(--color-primary-dark) !important;
  border-color: var(--color-primary-dark) !important;
}
.el-tabs__item.is-active { color: var(--color-primary) !important; }
.el-tabs__active-bar { background: var(--color-primary) !important; }
.el-tabs__item:hover { color: var(--color-primary) !important; }

/* el-main */
.el-main {
  background: var(--color-bg);
  padding: 20px;
  overflow-y: auto;
  overflow-x: hidden;
}
.el-main.has-topbar {
  padding-top: calc(var(--topbar-height) + 12px);
}

/* ===== 侧边栏（蓝色调浅色） ===== */
.app-aside {
  background: #DBEAFE;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
  box-shadow: 2px 0 8px rgba(37,99,235,0.08);
}
.drawer-inner {
  height: 100%;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 22px 20px 18px;
  margin-bottom: 4px;
}
.brand-icon { font-size: 22px; }
.brand-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-primary);
  letter-spacing: 0.5px;
}

.side-nav {
  flex: 1;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.nav-item {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1.5px solid var(--color-primary);
  color: var(--color-primary);
  background: #fff;
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
  box-shadow: none;
}
.nav-item:hover {
  background: #EEF2FF;
  color: var(--color-primary);
}
.nav-item.active {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
  box-shadow: 0 2px 8px rgba(37,99,235,0.25);
  font-weight: 700;
}
.nav-icon { font-size: 15px; }

.side-footer {
  padding: 14px 10px 16px;
  margin-top: 4px;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.user-name {
  font-size: 13px;
  color: var(--color-text);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 0 4px;
}
.side-btn {
  width: 100%;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1.5px solid var(--color-primary);
  background: #fff;
  color: var(--color-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.side-btn:hover {
  background: #EEF2FF;
  color: var(--color-primary);
}
.side-btn.danger {
  border-color: #ef4444;
  color: #ef4444;
  background: #fff;
}
.side-btn.danger:hover {
  background: #fee2e2;
  color: #dc2626;
  border-color: #dc2626;
}

/* ===== 移动端顶栏（浅色） ===== */
.mobile-topbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: var(--topbar-height);
  background: #EFF6FF;
  display: flex;
  align-items: center;
  padding: 0 12px;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(37,99,235,0.10);
}
.topbar-menu-btn {
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  line-height: 1;
}
.topbar-menu-btn:hover {
  background: var(--color-bg);
  color: var(--color-primary);
}
.topbar-title {
  flex: 1;
  color: var(--color-text);
  font-size: 16px;
  font-weight: 600;
  text-align: center;
}
.topbar-user {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 移动端抽屉内边距清零 */
.mobile-drawer .el-drawer__body {
  padding: 0 !important;
  overflow: hidden;
}
</style>
