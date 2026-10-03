import type { Core } from '@strapi/strapi';

// Admin RBAC actions: they appear under Settings → Roles → Plugins → Comment moderation.
const bootstrap = async ({ strapi }: { strapi: Core.Strapi }) => {
  await strapi.admin.services.permission.actionProvider.registerMany([
    { section: 'plugins', displayName: 'Read the moderation queue', uid: 'read', pluginName: 'comment-moderation' },
    { section: 'plugins', displayName: 'Approve and reject comments', uid: 'moderate', pluginName: 'comment-moderation' },
  ]);
};

export default bootstrap;
