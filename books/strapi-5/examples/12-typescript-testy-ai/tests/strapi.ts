import fs from 'node:fs';
import path from 'node:path';
import { createStrapi } from '@strapi/strapi';
import type { Core } from '@strapi/strapi';

// Vitest runs from the project root, like the Strapi CLI.
const appDir = process.cwd();

function removeDatabase() {
  const file = path.join(appDir, process.env.DATABASE_FILENAME ?? '');
  fs.rmSync(file, { force: true });
}

/** Boots a full Strapi instance (no HTTP listener) on an empty SQLite file. */
export async function startStrapi(): Promise<Core.Strapi> {
  removeDatabase();
  const strapi = createStrapi({ appDir, distDir: path.join(appDir, 'dist') });
  await strapi.load();
  // listen() would mount the routers; supertest needs them without a fixed port.
  strapi.server.mount();
  return strapi;
}

export async function stopStrapi(strapi: Core.Strapi) {
  await strapi.destroy();
  removeDatabase();
}
