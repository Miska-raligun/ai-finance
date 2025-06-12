<template>
  <div class="login-box">
    <el-card class="box-card">
      <template #header>用户登录</template>
      <el-input v-model="username" placeholder="用户名" style="margin-bottom:10px" />
      <el-input v-model="password" placeholder="密码" type="password" style="margin-bottom:10px" />
      <div style="display:flex; gap:10px;">
        <el-button type="primary" @click="onLogin">登录</el-button>
        <el-button @click="onRegister">注册</el-button>
      </div>
      <p class="register-tip">新用户请输入用户名和密码后点击注册即可登录</p>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'

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
    if (data.is_admin) {
      localStorage.setItem('is_admin', '1')
    } else {
      localStorage.removeItem('is_admin')
    }
    router.push('/chat')
  } else {
    alert(data.error || '登录失败')
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
    alert(data.error || '注册失败')
  }
}
</script>

<style scoped>
.login-box {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  height: 100dvh;
}
.register-tip {
  color: #888;
  margin-top: 10px;
  font-size: 13px;
}
</style>
