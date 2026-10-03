import { factories } from '@strapi/strapi';
import { slugify } from '../../../document-middlewares/article-derived-fields';

export default factories.createCoreService('api::category.category', ({ strapi }) => ({
  // Imports a category with its first articles: all of them land in the database or none does.
  async importWithArticles(name: string, titles: string[]) {
    return strapi.db.transaction(async ({ onCommit }) => {
      const category = await strapi.documents('api::category.category').create({
        data: { name, slug: name.toLowerCase() },
      });
      for (const title of titles) {
        await strapi.documents('api::article.article').create({
          data: { title, slug: slugify(title), category: category.documentId },
        });
      }
      onCommit(() => strapi.log.info(`Imported ${name} with ${titles.length} article(s)`));
      return category;
    });
  },
}));
