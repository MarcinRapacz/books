import type { Core } from '@strapi/strapi';
import { newCommentEmail } from './notifications/new-comment-email';
import { ensureFrontendWebhook } from './setup/webhooks';
import { ensurePolishLocale } from './setup/i18n';

const UPLOAD_ACTION = 'plugin::upload.content-api.upload';

// Authors may upload covers; chapter 7 explains permissions set from code.
async function allowAuthenticatedUpload(strapi: Core.Strapi) {
  const role = await strapi.db.query('plugin::users-permissions.role').findOne({ where: { type: 'authenticated' } });
  const permissions = strapi.db.query('plugin::users-permissions.permission');
  if (role && !(await permissions.findOne({ where: { action: UPLOAD_ACTION, role: role.id } }))) {
    await permissions.create({ data: { action: UPLOAD_ACTION, role: role.id } });
  }
}

export default {
  register({ strapi }: { strapi: Core.Strapi }) {
    strapi.documents.use(newCommentEmail(strapi));
  },

  async bootstrap({ strapi }: { strapi: Core.Strapi }) {
    await ensurePolishLocale(strapi);
    await allowAuthenticatedUpload(strapi);
    await ensureFrontendWebhook(strapi);
  },
};
