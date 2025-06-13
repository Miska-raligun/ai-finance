<!-- src/App.vue 最终版本 -->
<template>
  <el-container style="height: 100vh; height: 100dvh">
    <el-aside v-if="!isMobile && route.path !== '/login'" width="200px" class="app-aside">
      <el-menu
        :default-active="active"
        class="el-menu-vertical-demo app-menu"
        @select="handleSelect"
        router
      >
        <el-menu-item index="/chat">💬 聊天记账</el-menu-item>
        <el-menu-item index="/ledger">📒 账本管理</el-menu-item>
        <el-menu-item v-if="isAdmin" index="/admin">🛠 用户管理</el-menu-item>
      </el-menu>
      <el-card class="user-panel" shadow="never">
        <template #header>
          <div class="user-title">当前用户：{{ username }}</div>
        </template>
        <div class="user-actions">
          <el-button type="primary" @click="logout">退出</el-button>  
        </div>
        <div class="user-actions">
          <el-button @click="openConfigPanel">配置模型</el-button>  
        </div>
      </el-card>
    </el-aside>
    <el-drawer
      v-if="isMobile && route.path !== '/login'"
      v-model="showDrawer"
      :with-header="false"
      size="200px"
      class="app-aside"
      direction="ltr"
    >
      <el-menu
        :default-active="active"
        class="el-menu-vertical-demo app-menu"
        @select="handleSelect"
        router
      >
        <el-menu-item index="/chat">💬 聊天记账</el-menu-item>
        <el-menu-item index="/ledger">📒 账本管理</el-menu-item>
        <el-menu-item v-if="isAdmin" index="/admin">🛠 用户管理</el-menu-item>
      </el-menu>
      <el-card class="user-panel" shadow="never">
        <template #header>
          <div class="user-title">当前用户：{{ username }}</div>
        </template>
        <div class="user-actions">
          <el-button type="primary" @click="logout">退出</el-button>
        </div>
        <div class="user-actions">
          <el-button @click="openConfigPanel">配置模型</el-button>
        </div>
      </el-card>
    </el-drawer>

    <el-container>
      <el-main>
        <el-button class="mobile-menu-btn" v-if="isMobile && route.path !== '/login'" @click="showDrawer = true">☰</el-button>
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
        <el-dialog v-model="showConfig" title="LLM 设置" width="400px">
          <el-form label-width="80px">
            <el-form-item label="URL">
              <el-input v-model="llmUrl" placeholder="https://api.example.com" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="llmKey" />
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input v-model="llmModel" placeholder="Pro/deepseek-ai/DeepSeek-V3" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="useDefault">加载系统默认配置</el-button>
            <el-button type="primary" @click="saveConfig">保存</el-button>
          </template>
        </el-dialog>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { ref, watchEffect, onMounted, watch, onBeforeUnmount } from 'vue'
import api from '@/api'

const route = useRoute()
const router = useRouter()
const active = ref(route.path)
const showConfig = ref(false)
const llmUrl = ref('')
const llmKey = ref('')
const llmModel = ref('')
const username = ref('')
const isAdmin = ref(false)
const isMobile = ref(window.innerWidth < 600)
const showDrawer = ref(false)

function updateIsMobile() {
  isMobile.value = window.innerWidth < 600
}

onMounted(() => {
  updateIsMobile()
  window.addEventListener('resize', updateIsMobile)
})
onBeforeUnmount(() => window.removeEventListener('resize', updateIsMobile))

watchEffect(() => {
  active.value = route.path
})

function updateUsername() {
  api
    .get('/api/me')
    .then(res => {
      username.value = res.data.username || ''
      isAdmin.value = !!res.data.is_admin
      if (res.data.username) {
        localStorage.setItem('username', res.data.username)
      } else {
        localStorage.removeItem('username')
      }
      if (res.data.is_admin) {
        localStorage.setItem('is_admin', '1')
      } else {
        localStorage.removeItem('is_admin')
      }
    })
    .catch(() => {
      username.value = ''
      isAdmin.value = false
      localStorage.removeItem('username')
      localStorage.removeItem('is_admin')
    })
}

onMounted(updateUsername)
watch(() => route.path, updateUsername)

function checkConfig() {
  if (route.path !== '/login' && !localStorage.getItem('llmConfig')) {
    showConfig.value = true
  }
}

onMounted(checkConfig)
watch(() => route.path, checkConfig)

function saveConfig() {
  const cfg = {
    url: llmUrl.value,
    apikey: llmKey.value,
    model: llmModel.value
  }
  localStorage.setItem('llmConfig', JSON.stringify(cfg))
  showConfig.value = false
}

function useDefault() {
  localStorage.setItem('llmConfig', 'default')
  showConfig.value = false
}

function handleSelect(index) {
  router.push(index)
  if (isMobile.value) showDrawer.value = false
}

function logout() {
  fetch('/api/logout', { method: 'POST', credentials: 'include' }).catch(() => {})
  localStorage.removeItem('username')
  localStorage.removeItem('is_admin')
  router.push('/login')
}

function openConfigPanel() {
  showConfig.value = true
}
</script>

<style>
body {
  margin: 0;
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
}
.user-panel {
  margin: 10px;
  padding: 10px;
}

.user-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-actions .el-button {
  width: 100%;
}

.app-aside {
  background: #f5f5f5;
  display: flex;
  flex-direction: column;
}

.app-menu {
  flex-grow: 1;
}

.mobile-menu-btn {
  position: fixed;
  top: 10px;
  left: 10px;
  z-index: 1000;
}

@media (min-width: 600px) {
  .mobile-menu-btn {
    display: none;
  }
}
</style>




