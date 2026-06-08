// vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    // Element Plus 按需引入：扫 <template> 里的 <el-*> 自动注入对应组件 + CSS。
    // ElMessage/ElMessageBox 这类命令式 API 仍然由 `import { ElMessage } from 'element-plus'`
    // 显式引入；resolver 会顺带把它们的样式补上，主 bundle 不再扛全量 EP。
    AutoImport({ resolvers: [ElementPlusResolver()] }),
    Components({ resolvers: [ElementPlusResolver()] }),
  ],
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
    // 大图表库继续单独拆 chunk（vendor-echarts/vendor-chartjs）；
    // EP 经按需引入后体积已显著缩小，按 rollup 默认即可与主 bundle 自然分裂。
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
