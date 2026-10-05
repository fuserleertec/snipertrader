import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const yahooProxy = {
  target: 'https://query1.finance.yahoo.com',
  changeOrigin: true,
  rewrite: (path: string) => path.replace(/^\/market/, ''),
  configure: (proxy: { on: (ev: string, fn: (...args: never[]) => void) => void }) => {
    proxy.on('proxyReq', ((proxyReq: { setHeader: (k: string, v: string) => void }) => {
      proxyReq.setHeader('User-Agent', 'Mozilla/5.0 (compatible; MeridianEquities/1.0)');
      proxyReq.setHeader('Accept', 'application/json');
    }) as never);
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    host: true,
    proxy: { '/market': yahooProxy },
  },
  preview: {
    port: 5174,
    strictPort: true,
    host: true,
    proxy: { '/market': yahooProxy },
  },
});
