import type { Core } from '@strapi/strapi';

// Content API routes of a plugin get users-permissions actions like any API:
// plugin::<plugin-name>.<controller>.<action>.
const ROLE_PERMISSIONS: Record<string, string[]> = {
  public: ['plugin::comment-moderation.comments.findApproved'],
  authenticated: [
    'plugin::comment-moderation.comments.findApproved',
    'plugin::comment-moderation.comments.report',
    'plugin::upload.content-api.upload',
  ],
};

export default {
  register() {},

  async bootstrap({ strapi }: { strapi: Core.Strapi }) {
    for (const [roleType, actions] of Object.entries(ROLE_PERMISSIONS)) {
      const role = await strapi.db
        .query('plugin::users-permissions.role')
        .findOne({ where: { type: roleType } });
      if (!role) {
        continue;
      }
      for (const action of actions) {
        const exists = await strapi.db
          .query('plugin::users-permissions.permission')
          .findOne({ where: { action, role: role.id } });
        if (!exists) {
          await strapi.db
            .query('plugin::users-permissions.permission')
            .create({ data: { action, role: role.id } });
        }
      }
    }
  },
};
