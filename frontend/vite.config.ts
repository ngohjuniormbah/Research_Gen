import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Proxy API calls to the backend during local development.
    // Adjust the target to match wherever the backend service runs.
    proxy: {
      '/api': {
        target: 'https://litreview-web.onrender.com',
        changeOrigin: true,
        secure: true,
      },
      '/healthz': {
        target: 'https://litreview-web.onrender.com',
        changeOrigin: true,
        secure: true,
      },
    },
  },
});