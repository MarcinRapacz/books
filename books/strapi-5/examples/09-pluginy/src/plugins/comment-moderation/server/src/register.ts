import type { Core } from '@strapi/strapi';
import { z } from '@strapi/utils';
import type { ModerationService } from './services/moderation';

const commentSchema = z.object({
  documentId: z.string(),
  body: z.string(),
  article: z.string().nullable(),
});

const register = ({ strapi }: { strapi: Core.Strapi }) => {
  // MCP tools must be registered while the MCP server is idle, i.e. in register().
  strapi.ai.mcp.registerTool({
    name: 'list_pending_comments',
    title: 'List pending comments',
    description: 'Returns the oldest comments waiting for moderation in the Redakcja magazine.',
    auth: { policies: [{ action: 'plugin::comment-moderation.read' }] },
    resolveInputSchema: () => z.object({ page: z.number().int().min(1).default(1) }),
    resolveOutputSchema: () => z.object({ total: z.number(), comments: z.array(commentSchema) }),
    createHandler: (strapi) => async ({ args }) => {
      const { results, pagination } = await strapi
        .plugin('comment-moderation').service<ModerationService>('moderation').findPending(args.page);
      const comments = results.map(({ documentId, body, article }) => ({ documentId, body, article }));
      return {
        content: [{ type: 'text', text: JSON.stringify(comments) }],
        structuredContent: { total: pagination.total, comments },
      };
    },
  });
};

export default register;
