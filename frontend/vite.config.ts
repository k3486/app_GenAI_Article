/// <reference types="vitest/config" />
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  server: {
    host: true,
    port: 5173,
    // /api はバックエンド(FastAPI)へ転送。同一オリジンになるので CORS 不要
    proxy: { '/api': 'http://localhost:8000' },
    // Windows 側のフォルダ（9p）では、ファイルの変更が通知されない。定期的に確認して画面に反映する
    watch: { usePolling: true, interval: 300 },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
