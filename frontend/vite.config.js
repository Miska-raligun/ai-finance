// vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    open: true,
    proxy: {
      '/api': 'http://localhost:5000'
    }
  },
  resolve: {
    alias: {
      '@': '/src'
    }
  },
  build: {
    // 把重型库拆到独立 chunk，避免登录/聊天页也下载图表代码。
    // 各 chunk 由对应路由的 dynamic import 触发加载。
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-vue': ['vue', 'vue-router', 'pinia'],
          'vendor-element': ['element-plus'],
          'vendor-echarts': ['echarts', 'vue-echarts'],
          'vendor-chartjs': ['chart.js']
        }
      }
    }
  }
})

