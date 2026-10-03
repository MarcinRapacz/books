import { ExternalLink } from '@strapi/icons';
import type { HeaderActionComponent } from '@strapi/content-manager/strapi-admin';

// Inlined into the admin bundle at build time (only STRAPI_ADMIN_* variables are exposed).
const FRONTEND_URL = process.env.STRAPI_ADMIN_FRONTEND_URL ?? 'http://localhost:3000';

export const OpenOnSiteAction: HeaderActionComponent = ({ model, document }) => {
  // Header actions are rendered for every content type, so the action filters itself out.
  if (model !== 'api::article.article') {
    return null;
  }
  const slug: unknown = document?.slug;
  const hasPublishedVersion = document !== undefined && document.status !== 'draft';

  return {
    label: 'Otwórz na stronie',
    icon: <ExternalLink />,
    disabled: typeof slug !== 'string' || !hasPublishedVersion,
    onClick: () => {
      window.open(`${FRONTEND_URL}/articles/${String(slug)}`, '_blank', 'noopener');
    },
  };
};
