import type { Core } from '@strapi/strapi';

type CommentPolicyContext = Core.PolicyContext & {
  request: { body?: { data?: { article?: unknown } } };
};

// Readers may comment only on articles that have a published version.
export default async (
  policyContext: CommentPolicyContext,
  _config: unknown,
  { strapi }: { strapi: Core.Strapi }
): Promise<boolean> => {
  const articleId = policyContext.request.body?.data?.article;
  if (typeof articleId !== 'string') {
    return false;
  }

  const published = await strapi.documents('api::article.article').count({
    filters: { documentId: articleId },
    status: 'published',
  });

  return published > 0;
};
