import type { Core } from '@strapi/strapi';

export default ({ env }: Core.Config.Shared.ConfigParams) => ({
  commentsPerHour: env.int('COMMENTS_PER_HOUR', 10),
  moderationEnabled: env.bool('COMMENT_MODERATION', true),
});
