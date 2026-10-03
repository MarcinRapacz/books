import type { Core } from '@strapi/strapi';

const config = ({ env }: Core.Config.Shared.ConfigParams): Core.Config.Admin => ({
  autoOpen: false,
  preview: {
    enabled: true,
    config: {
      allowedOrigins: [env('CLIENT_URL', 'http://localhost:3000')],
      async handler(uid, { documentId, locale, status }) {
        // Returning null hides the preview button for types without a frontend page.
        if (uid !== 'api::article.article') return null;
        const article = await strapi.documents(uid).findOne({
          documentId,
          locale,
          status: status === 'published' ? 'published' : 'draft',
          fields: ['slug'],
        });
        if (!article) return null;
        // The frontend checks the secret, enables its draft mode and redirects to `url` (chapter 11).
        const params = new URLSearchParams({
          url: `/artykuly/${article.slug}`,
          secret: env('PREVIEW_SECRET', ''),
          status: status ?? 'draft',
        });
        return `${env('CLIENT_URL', 'http://localhost:3000')}/api/preview?${params}`;
      },
    },
  },
  auth: {
    secret: env('ADMIN_JWT_SECRET')!,
  },
  apiToken: {
    salt: env('API_TOKEN_SALT')!,
  },
  transfer: {
    token: {
      salt: env('TRANSFER_TOKEN_SALT')!,
    },
  },
  secrets: {
    encryptionKey: env('ENCRYPTION_KEY')!,
  },
  flags: {
    nps: env.bool('FLAG_NPS', true),
    promoteEE: env.bool('FLAG_PROMOTE_EE', true),
    docLinks: env.bool('FLAG_DOC_LINKS', true),
  },
});

export default config;
