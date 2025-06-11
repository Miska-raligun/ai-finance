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
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('')
const password = ref('')

async function onLogin() {
  const res = await fetch('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username.value, password: password.value })
  })
  const data = await res.json()
  if (data.token) {
    localStorage.setItem('token', data.token)
    router.push('/chat')
  } else {
    alert(data.error || '登录失败')
  }
}

async function onRegister() {
  const res = await fetch('/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username.value, password: password.value })
  })
  const data = await res.json()
  if (data.success) {
    alert('注册成功，请登录')
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
}
</style>
