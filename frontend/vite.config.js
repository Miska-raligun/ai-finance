// vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/chat': 'http://localhost:5000',
      '/login': 'http://localhost:5000',
      '/register': 'http://localhost:5000',
      '/records': 'http://localhost:5000',
      '/categories': 'http://localhost:5000',
      '/budgets': 'http://localhost:5000',
      '/income': 'http://localhost:5000',
      '/stats': 'http://localhost:5000'
    }
  },
  resolve: {
    alias: {
      '@': '/src'
    }
  }
})

