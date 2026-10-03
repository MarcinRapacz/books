import type { Core } from '@strapi/strapi';
import { errors } from '@strapi/utils';

// Content types that have an `author` relation to users-permissions users.
type IsOwnerConfig = { uid: 'api::article.article' | 'api::comment.comment' };

// Core.PolicyContext does not declare Koa's `state` and the router's `params`.
type OwnerPolicyContext = Core.PolicyContext & {
  state: { user?: { id: number } };
  params: { id?: string };
};

export default async (
  policyContext: OwnerPolicyContext,
  config: IsOwnerConfig,
  { strapi }: { strapi: Core.Strapi }
): Promise<boolean> => {
  const user = policyContext.state.user;
  const documentId = policyContext.params.id;
  if (!user || !documentId) {
    return false;
  }

  const entry = await strapi.documents(config.uid).findOne({
    documentId,
    fields: ['documentId'],
    populate: { author: { fields: ['id'] } },
  });

  // Unknown document: let the controller answer with its regular 404.
  if (!entry) {
    return true;
  }
  if (entry.author?.id === user.id) {
    return true;
  }

  throw new errors.PolicyError('You can only modify your own entries', {
    policy: 'is-owner',
  });
};
