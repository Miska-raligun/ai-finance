<template>
  <div class="login-page">
    <div class="login-card">
      <img src="/favicon.ico" class="login-logo" alt="Anon" />
      <h1 class="login-title">智能记账助手Anon</h1>
      <p class="login-sub">管理你的每一笔收支</p>

      <div class="login-form">
        <div class="field">
          <label class="field-label">用户名</label>
          <el-input
            v-model="username"
            placeholder="请输入用户名"
            size="large"
            @keyup.enter="isRegister ? onRegister() : onLogin()"
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
            @keyup.enter="isRegister ? onRegister() : onLogin()"
          />
        </div>

        <!-- 注册模式：验证码 -->
        <div v-if="isRegister" class="field">
          <label class="field-label">验证码</label>
          <div class="captcha-row">
            <img
              :src="captchaUrl"
              class="captcha-img"
              @click="refreshCaptcha"
              title="点击刷新验证码"
              alt="验证码"
            />
            <el-input
              v-model="captchaInput"
              placeholder="输入图中字符"
              size="large"
              maxlength="4"
              style="flex: 1"
              @keyup.enter="onRegister"
            />
          </div>
          <span class="captcha-hint">不区分大小写，点击图片刷新</span>
        </div>

        <div class="btn-row">
          <el-button
            v-if="!isRegister"
            type="primary"
            size="large"
            class="action-btn"
            @click="onLogin"
          >登录</el-button>
          <el-button
            v-else
            type="primary"
            size="large"
            class="action-btn"
            @click="onRegister"
          >注册</el-button>
        </div>

        <div class="switch-row">
          <template v-if="!isRegister">
            没有账号？<el-link type="primary" @click="switchToRegister">立即注册</el-link>
          </template>
          <template v-else>
            已有账号？<el-link type="primary" @click="switchToLogin">返回登录</el-link>
          </template>
        </div>
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
const isRegister = ref(false)
const captchaToken = ref('')
const captchaInput = ref('')
const captchaUrl = ref('')

function reset() {
  username.value = ''
  password.value = ''
  isRegister.value = false
  captchaInput.value = ''
  captchaToken.value = ''
  captchaUrl.value = ''
}
onMounted(reset)
onActivated(reset)

async function refreshCaptcha() {
  const res = await fetch('/api/captcha')
  const data = await res.json()
  captchaToken.value = data.token || ''
  captchaUrl.value = data.image || ''
  captchaInput.value = ''
}

function switchToRegister() {
  isRegister.value = true
  refreshCaptcha()
}

function switchToLogin() {
  isRegister.value = false
  captchaInput.value = ''
  captchaToken.value = ''
  captchaUrl.value = ''
}

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
    body: JSON.stringify({
      username: username.value,
      password: password.value,
      captcha_token: captchaToken.value,
      captcha_input: captchaInput.value
    })
  })
  const data = await res.json()
  if (data.success) {
    ElMessage.success('注册成功，正在登录…')
    await onLogin()
  } else {
    ElMessage.error(data.error || '注册失败')
    refreshCaptcha()
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
  background: linear-gradient(145deg, #DBEAFE 0%, #EFF6FF 50%, #BFDBFE 100%);
  padding: 20px;
}

.login-card {
  background: rgba(255, 255, 255, 0.97);
  border-radius: 20px;
  padding: 40px 36px;
  width: 100%;
  max-width: 380px;
  box-shadow: 0 8px 40px rgba(79,70,229,0.12), 0 2px 8px rgba(0,0,0,0.06);
  border: 1px solid rgba(79,70,229,0.1);
  text-align: center;
}

.login-logo {
  width: 72px;
  height: 72px;
  border-radius: 18px;
  object-fit: cover;
  margin-bottom: 14px;
  box-shadow: 0 2px 10px rgba(79,70,229,0.15);
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

.captcha-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.captcha-img {
  height: 44px;
  width: 120px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  cursor: pointer;
  flex-shrink: 0;
  object-fit: cover;
  transition: opacity 0.15s;
}
.captcha-img:hover { opacity: 0.85; }

.captcha-hint {
  font-size: 12px;
  color: #94a3b8;
}

.btn-row {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}

.action-btn {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  border-radius: 10px !important;
  height: 44px !important;
}

.switch-row {
  text-align: center;
  font-size: 13px;
  color: #64748b;
}
</style>
