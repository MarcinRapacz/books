import type { Core, Modules } from '@strapi/strapi';
import { errors } from '@strapi/utils';

export const categoryDeleteGuard = (strapi: Core.Strapi): Modules.Documents.Middleware.Middleware => {
  return async (context, next) => {
    if (context.uid !== 'api::category.category' || context.action !== 'delete') return next();

    const { documentId } = context.params;
    const articles = await strapi.documents('api::article.article').count({
      filters: { category: { documentId } },
    });
    if (articles > 0) {
      throw new errors.ApplicationError(
        `Category has ${articles} article(s). Move them to another category first.`,
        { documentId, articles }
      );
    }
    return next();
  };
};
