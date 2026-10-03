import { createRequire } from 'node:module';
import { defineConfig } from 'vitest/config';

const require = createRequire(import.meta.url);

export default defineConfig({
  resolve: {
    // The ESM build of @strapi/core fails in Node's ESM loader (directory import of lodash/fp).
    // Point Vitest at the CommonJS build, the one `strapi develop` runs.
    alias: { '@strapi/strapi': require.resolve('@strapi/strapi') },
  },
  test: {
    include: ['tests/**/*.test.ts'],
    // strapi.destroy() calls process.removeAllListeners(), which cuts the IPC channel of a
    // forked worker; worker threads survive it.
    pool: 'threads',
    setupFiles: ['tests/env.ts'],
    // Booting Strapi and syncing a fresh SQLite schema takes a few seconds per test file.
    hookTimeout: 60_000,
  },
});
