<!-- src/views/LedgerView.vue -->
<template>
  <el-container style="height: 100%;">
    <el-header><h2>📒 我的账本</h2></el-header>
    <el-main>
      <el-row :gutter="20">
        <el-col :span="8"><CategoryManager :refreshFlag="refreshFlag" /></el-col>
        <el-col :span="8"><BudgetManager :refreshFlag="refreshFlag" /></el-col>
        <el-col :span="8"><SpendCharts :refreshFlag="refreshFlag" /></el-col>
        <el-col :span="24"><RecordTable :refreshFlag="refreshFlag" /></el-col>
      </el-row>
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, onActivated } from 'vue'
import CategoryManager from '../components/CategoryManager.vue'
import BudgetManager from '../components/BudgetManager.vue'
import SpendCharts from '../components/SpendCharts.vue'
import RecordTable from '../components/RecordTable.vue'

const refreshFlag = ref(0)

onActivated(() => {
  refreshFlag.value++
})
</script>


