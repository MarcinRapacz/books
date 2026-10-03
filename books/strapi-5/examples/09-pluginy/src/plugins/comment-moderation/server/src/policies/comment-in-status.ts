import type { Core } from '@strapi/strapi';
import { errors } from '@strapi/utils';
import type { ModerationService, ModerationStatus } from '../services/moderation';

type CommentInStatusConfig = { statuses?: ModerationStatus[] };

const commentInStatus = async (
  policyContext: Core.PolicyContext & { params: { id?: string } },
  config: CommentInStatusConfig,
  { strapi }: { strapi: Core.Strapi }
): Promise<boolean> => {
  const allowed = config.statuses ?? [];
  const documentId = policyContext.params.id;
  if (!documentId || allowed.length === 0) return false;
  const status = await strapi.plugin('comment-moderation')
    .service<ModerationService>('moderation').getStatus(documentId);
  // Unknown comment: the controller answers with its regular 404.
  if (status === null || allowed.includes(status)) return true;
  throw new errors.PolicyError('Comment is not in an allowed moderation status', {
    policy: 'comment-in-status', moderationStatus: status, allowed,
  });
};

export default commentInStatus;
