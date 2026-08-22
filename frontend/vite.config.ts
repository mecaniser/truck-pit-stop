import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ command, mode }) => {
  const runtimeBranch = process.env.VITE_DIESELBRIDGE_RUNTIME_BRANCH ?? ''
  const runtimeSha = process.env.VITE_DIESELBRIDGE_RUNTIME_SHA ?? ''
  const isLocalRuntimeServe = command === 'serve' && mode !== 'test'

  if (isLocalRuntimeServe) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$/.test(runtimeBranch)) {
      throw new Error('VITE_DIESELBRIDGE_RUNTIME_BRANCH must be a validated branch name')
    }
    if (!/^[0-9a-f]{40}$/.test(runtimeSha)) {
      throw new Error('VITE_DIESELBRIDGE_RUNTIME_SHA must be a full lowercase commit SHA')
    }
  }

  return {
  define: isLocalRuntimeServe ? {
    'import.meta.env.VITE_DIESELBRIDGE_RUNTIME_BRANCH': JSON.stringify(runtimeBranch),
    'import.meta.env.VITE_DIESELBRIDGE_RUNTIME_SHA': JSON.stringify(runtimeSha),
  } : undefined,
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    css: true,
  },
  }
})
