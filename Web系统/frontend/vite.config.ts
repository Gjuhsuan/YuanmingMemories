import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9090',
        changeOrigin: true,
        // SSE 需要禁用代理缓冲
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            if (req.url?.includes('/api/chat')) {
              proxyReq.setHeader('Connection', 'keep-alive')
            }
          })
        },
      },
      '/static': {
        target: 'http://127.0.0.1:9090',
        changeOrigin: true,
      },
    },
  },
})
