import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

// https://vitejs.dev/config/
export default defineConfig(({ command }) => ({
  plugins: command === 'build' ? [react(), viteSingleFile()] : [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
  },
  build: {
    emptyOutDir: false,
    minify: true,
    cssCodeSplit: false, // Ensure CSS is inlined
    assetsInlineLimit: 100000000, // Large limit to ensure assets are inlined
  }
}))
