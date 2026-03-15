<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo">💰</div>
      <h1 class="login-title">智能记账助手</h1>
      <p class="login-sub">管理你的每一笔收支</p>

      <div class="login-form">
        <div class="field">
          <label class="field-label">用户名</label>
          <el-input
            v-model="username"
            placeholder="请输入用户名"
            size="large"
            @keyup.enter="onLogin"
          />
        </div>
        <div class="field">
          <label class="field-label">密码</label>
          <el-input
            v-model="password"
            placeholder="请输入密码"
            type="password"
            size="large"
            show-password
            @keyup.enter="onLogin"
          />
        </div>
        <el-button type="primary" size="large" class="login-btn" @click="onLogin">
          登 录
        </el-button>
        <el-button size="large" class="register-btn" @click="onRegister">
          注 册
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const router = useRouter()
const username = ref('')
const password = ref('')

function reset() {
  username.value = ''
  password.value = ''
}
onMounted(reset)
onActivated(reset)

async function onLogin() {
  const res = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ username: username.value, password: password.value })
  })
  const data = await res.json()
  if (data.success) {
    localStorage.setItem('username', username.value)
    if (data.is_admin) localStorage.setItem('is_admin', '1')
    else localStorage.removeItem('is_admin')
    router.push('/chat')
  } else {
    ElMessage.error(data.error || '登录失败')
  }
}

async function onRegister() {
  const res = await fetch('/api/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ username: username.value, password: password.value })
  })
  const data = await res.json()
  if (data.success) {
    await onLogin()
  } else {
    ElMessage.error(data.error || '注册失败')
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 60%, #2563EB 100%);
  padding: 20px;
}

.login-card {
  background: rgba(255, 255, 255, 0.97);
  border-radius: 20px;
  padding: 40px 36px;
  width: 100%;
  max-width: 380px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2), 0 4px 16px rgba(79,70,229,0.2);
  text-align: center;
}

.login-logo {
  font-size: 48px;
  margin-bottom: 12px;
  line-height: 1;
}

.login-title {
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 6px;
}

.login-sub {
  font-size: 14px;
  color: #64748b;
  margin: 0 0 28px;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  text-align: left;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.login-btn {
  width: 100%;
  margin-top: 4px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 2px;
  border-radius: 10px !important;
  height: 44px !important;
}

.register-btn {
  width: 100%;
  font-size: 15px;
  font-weight: 500;
  letter-spacing: 2px;
  border-radius: 10px !important;
  height: 44px !important;
  color: #4F46E5 !important;
  border-color: #4F46E5 !important;
}

.register-btn:hover {
  background: #EEF2FF !important;
}
</style>
