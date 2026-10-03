import type { Core } from '@strapi/strapi';
import { registerDocumentTrace } from './debug/trace-documents';
import { articleAuthor } from './document-middlewares/article-author';
import { articleDerivedFields } from './document-middlewares/article-derived-fields';
import { categoryDeleteGuard } from './document-middlewares/category-delete-guard';

export default {
  register({ strapi }: { strapi: Core.Strapi }) {
    registerDocumentTrace(strapi);
    strapi.documents.use(articleAuthor(strapi));
    strapi.documents.use(articleDerivedFields(strapi));
    strapi.documents.use(categoryDeleteGuard(strapi));
  },

  bootstrap() {},
};
