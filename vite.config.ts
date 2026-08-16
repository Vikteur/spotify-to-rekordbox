import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Follow whatever port the API was told to use, so PORT=8010 moves both.
const apiPort = process.env.PORT ?? '8000';

export default defineConfig({
  root: 'client',
  plugins: [react()],
  server: {
    proxy: {
      '/api': `http://127.0.0.1:${apiPort}`,
    },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
  },
});
