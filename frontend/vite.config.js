import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// TestFlow AI 가 5173/8000 을 쓰므로 여기는 5174/8001
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': 'http://localhost:8001',
    },
  },
  preview: { port: 5174 },
})
