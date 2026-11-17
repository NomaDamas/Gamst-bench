import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({ plugins: [react()], test: {
  environment: 'jsdom',
  setupFiles: ['./src/test-setup.ts'],
  // CI places the GAMST and GamstCrew source checkouts under .runtime.
  // Keep their own tests out of this benchmark's Vitest project.
  exclude: ['**/node_modules/**', '**/.git/**', '**/.runtime/**'],
} });
