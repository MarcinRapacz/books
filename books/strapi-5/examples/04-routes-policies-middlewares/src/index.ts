import type { Core } from '@strapi/strapi';

export default {
  register({ strapi }: { strapi: Core.Strapi }) {
    // Learning aid for chapter 4; Document Service middlewares are covered in chapter 6.
    strapi.documents.use(async (context, next) => {
      if (context.uid.startsWith('api::')) {
        strapi.log.info(`[trace] document service: ${context.action} ${context.uid}`);
      }
      return next();
    });
  },

  bootstrap() {},
};
