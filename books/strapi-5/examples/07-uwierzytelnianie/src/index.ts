import type { Core } from '@strapi/strapi';

// Permissions live in code, so every environment ends up with the same rules after a deploy.
// Keys are users-permissions role types; values are action UIDs.
const ROLE_PERMISSIONS: Record<string, string[]> = {
  authenticated: ['api::article.article.mine'],
};

const ensureRolePermissions = async (strapi: Core.Strapi) => {
  const roles = strapi.db.query('plugin::users-permissions.role');
  const permissions = strapi.db.query('plugin::users-permissions.permission');

  for (const [type, actions] of Object.entries(ROLE_PERMISSIONS)) {
    const role = await roles.findOne({ where: { type } });
    if (!role) {
      throw new Error(`users-permissions role "${type}" does not exist`);
    }
    for (const action of actions) {
      const granted = await permissions.count({ where: { action, role: role.id } });
      if (granted === 0) {
        await permissions.create({ data: { action, role: role.id } });
        strapi.log.info(`Granted ${action} to role ${type}`);
      }
    }
  }
};

type GrantProvider = { enabled: boolean; key: string; secret: string; callback: string };

// Provider settings normally live in the admin panel (plugin store, key "grant").
// Writing them from env keeps secrets out of the database dump and identical across environments.
const configureGithubProvider = async (strapi: Core.Strapi) => {
  const key = process.env.GITHUB_CLIENT_ID;
  const secret = process.env.GITHUB_CLIENT_SECRET;
  if (!key || !secret) {
    return;
  }
  const frontendCallback =
    process.env.GITHUB_FRONTEND_CALLBACK ?? 'http://localhost:3000/connect/github/redirect';

  const store = strapi.store({ type: 'plugin', name: 'users-permissions', key: 'grant' });
  const grant = (await store.get()) as Record<string, GrantProvider>;
  grant.github = { ...grant.github, enabled: true, key, secret, callback: frontendCallback };
  await store.set({ value: grant });
};

export default {
  register() {},

  async bootstrap({ strapi }: { strapi: Core.Strapi }) {
    await ensureRolePermissions(strapi);
    await configureGithubProvider(strapi);
  },
};
