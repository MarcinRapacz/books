import type { Core } from '@strapi/strapi';

// Production always runs on Postgres, whatever DATABASE_CLIENT says.
const config = ({ env }: Core.Config.Shared.ConfigParams): Core.Config.Database => {
  const required = (name: string): string => {
    const value = env(name);
    if (!value) {
      throw new Error(`${name} is required in production`);
    }
    return value;
  };

  return {
    connection: {
      client: 'postgres',
      connection: {
        host: env('DATABASE_HOST', 'db'),
        port: env.int('DATABASE_PORT', 5432),
        database: required('DATABASE_NAME'),
        user: required('DATABASE_USERNAME'),
        password: required('DATABASE_PASSWORD'),
        ssl: env.bool('DATABASE_SSL', false),
        schema: env('DATABASE_SCHEMA', 'public'),
      },
      // Docker drops idle connections, so the pool must be allowed to shrink to zero.
      pool: { min: 0, max: env.int('DATABASE_POOL_MAX', 10) },
      acquireConnectionTimeout: env.int('DATABASE_CONNECTION_TIMEOUT', 60000),
    },
  };
};

export default config;
