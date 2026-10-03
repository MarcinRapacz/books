import type { Core } from '@strapi/strapi';

// Experiment from chapter 6: logs every Document Service call on articles.
export const registerDocumentTrace = (strapi: Core.Strapi) => {
  if (process.env.TRACE_ARTICLE_EVENTS !== 'true') return;

  strapi.documents.use(async (context, next) => {
    if (context.uid !== 'api::article.article') return next();
    const { status } = context.params as { status?: string };
    strapi.log.info(`[document]  ${context.action} status=${status ?? '-'} trx=${strapi.db.inTransaction()}`);
    const result = await next();
    strapi.log.info(`[document]  ${context.action} done trx=${strapi.db.inTransaction()}`);
    return result;
  });
};
