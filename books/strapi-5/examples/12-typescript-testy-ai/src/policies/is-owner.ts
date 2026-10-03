import { errors } from '@strapi/utils';
import type { Policy } from '../types/request-context';

// Content types that have an `author` relation to users-permissions users.
type IsOwnerConfig = { uid: 'api::article.article' | 'api::comment.comment' };

const isOwner: Policy<IsOwnerConfig> = async (policyContext, config, { strapi }) => {
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

export default isOwner;
