import type { Core } from '@strapi/strapi';

// Merged over config/server.ts when NODE_ENV=test: quiet logs, no npm update check (tests run offline).
const config: Partial<Core.Config.Server> = {
  logger: {
    config: { level: 'warn' },
    updates: { enabled: false },
  },
};

export default config;
