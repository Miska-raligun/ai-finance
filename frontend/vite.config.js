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
    // 只把真正大的图表库拆出来按需加载（仅在 Reports / Investment / Ledger
    // 等用到 chart 的 view 才需要拉）。view 代码本身回归主 bundle，
    // 避免每次切路由都从网络拉 chunk 造成感知卡顿。
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-echarts': ['echarts', 'vue-echarts'],
          'vendor-chartjs': ['chart.js']
        }
      }
    }
  }
})

