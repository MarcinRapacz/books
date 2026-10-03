// Runs in every test worker before the test file. Values exist only for the test process:
// CI has no .env file, and tests must never touch the development database.
const defaults: Record<string, string> = {
  APP_KEYS: 'testKeyOne,testKeyTwo',
  API_TOKEN_SALT: 'test-api-token-salt',
  ADMIN_JWT_SECRET: 'test-admin-jwt-secret',
  TRANSFER_TOKEN_SALT: 'test-transfer-token-salt',
  ENCRYPTION_KEY: 'test-encryption-key',
  JWT_SECRET: 'test-jwt-secret',
  STRAPI_TELEMETRY_DISABLED: 'true',
};
for (const [key, value] of Object.entries(defaults)) {
  process.env[key] ??= value;
}
// One database file per worker, so test files can run in parallel.
process.env.DATABASE_CLIENT = 'sqlite';
process.env.DATABASE_FILENAME = `.tmp/test-${process.env.VITEST_POOL_ID ?? '0'}.db`;
