<!-- src/App.vue 最终版本 -->
<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" style="background: #f5f5f5;">
      <el-menu
        :default-active="active"
        class="el-menu-vertical-demo"
        @select="handleSelect"
        router
      >
        <el-menu-item index="/chat">💬 聊天记账</el-menu-item>
        <el-menu-item index="/ledger">📒 账本管理</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-main>
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { ref, watchEffect } from 'vue'

const route = useRoute()
const router = useRouter()
const active = ref(route.path)

watchEffect(() => {
  active.value = route.path
})

function handleSelect(index) {
  router.push(index)
}
</script>

<style>
body {
  margin: 0;
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
}
</style>


