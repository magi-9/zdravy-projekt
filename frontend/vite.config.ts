import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import pkg from './package.json' with { type: 'json' };

const devProxyTarget = process.env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000';
const hmrPort = process.env.VITE_HMR_PORT ? Number(process.env.VITE_HMR_PORT) : undefined;

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // package.json "version" je držaná v sync s koreňovým VERSION súborom
  // (release-please extra-files) — __APP_VERSION__ je z toho jediný zdroj pravdy vo frontende.
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    host: true,
    port: 3000,
    ...(hmrPort ? { hmr: { host: 'localhost', port: hmrPort, protocol: 'ws' } } : {}),
    proxy: {
      '/api': {
        target: devProxyTarget,
        changeOrigin: true,
      },
    },
  },
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/__tests__/setup.ts',
    // e2e/ patrí Playwrightu (`npm run test:e2e`) — vitest by tie špecky
    // spustil v jsdom bez prehliadača a spadli by na chýbajúcom `test` importe.
    exclude: ['node_modules/**', 'dist/**', 'e2e/**'],
    // Default 5000ms je na zdieľanom CI runneri (viac testov paralelne)
    // niekedy tesný pre testy s viacerými `waitFor`/`fireEvent` krokmi za
    // sebou — OrderPage.test.tsx padal flaky na "Test timed out in 5000ms"
    // aj keď lokálne prebehol v zlomku času (release/2026-09-11, CI run
    // 34648382372). Zvýšené namiesto úpravy jednotlivých testov.
    testTimeout: 15000,
  },
});
