import type { Core } from '@strapi/strapi';
import { errors, z } from '@strapi/utils';
import type { PluginConfig } from '../config';

export const COMMENT_UID = 'api::comment.comment';

export type ModerationStatus = 'pending' | 'approved' | 'rejected';

// The plugin is compiled without the app's generated types, so Document Service results are
// AnyDocument here. Parsing them states what the plugin expects from api::comment.comment.
const commentRow = z.object({
  documentId: z.string(),
  body: z.string().default(''),
  createdAt: z.coerce.string().optional(),
  moderationStatus: z.enum(['pending', 'approved', 'rejected']).optional(),
  article: z.object({ title: z.string() }).nullish(),
  author: z.object({ username: z.string() }).nullish(),
});
const commentRows = z.array(commentRow);

const moderation = ({ strapi }: { strapi: Core.Strapi }) => {
  const comments = () => strapi.documents(COMMENT_UID);
  // Read config on every call, not at module load, so overrides from config/plugins.ts apply.
  const config = <K extends keyof PluginConfig>(key: K) =>
    strapi.plugin('comment-moderation').config<PluginConfig[K]>(key);

  const preview = (body: string) => {
    const max = config('previewLength');
    return body.length > max ? `${body.slice(0, max)}…` : body;
  };

  return {
    async findPending(page: number) {
      const pageSize = config('pageSize');
      const filters = { moderationStatus: 'pending' as const };
      const [rows, total] = await Promise.all([
        comments().findMany({
          filters,
          sort: 'createdAt:asc',
          fields: ['body', 'createdAt'],
          populate: { article: { fields: ['title'] }, author: { fields: ['username'] } },
          start: (page - 1) * pageSize,
          limit: pageSize,
        }),
        comments().count({ filters }),
      ]);
      return {
        results: commentRows.parse(rows).map((row) => ({
          documentId: row.documentId,
          body: preview(row.body),
          createdAt: row.createdAt,
          article: row.article?.title ?? null,
          author: row.author?.username ?? null,
        })),
        pagination: { page, pageSize, total },
      };
    },

    async setStatus(documentId: string, moderationStatus: ModerationStatus) {
      const updated = await comments().update({
        documentId,
        data: { moderationStatus } as Record<string, unknown>,
        fields: ['moderationStatus'],
      });
      if (!updated) {
        throw new errors.NotFoundError('Comment not found');
      }
      const { moderationStatus: saved } = commentRow.parse(updated);
      return { documentId, moderationStatus: saved };
    },

    async findApproved(articleDocumentId: string) {
      const rows = await comments().findMany({
        filters: { moderationStatus: 'approved', article: { documentId: articleDocumentId } },
        sort: 'createdAt:asc',
        fields: ['body', 'createdAt'],
        populate: { author: { fields: ['username'] } },
        limit: config('pageSize'),
      });
      // Explicit output shape: nothing from the user relation leaks besides the username.
      return commentRows.parse(rows).map((row) => ({
        documentId: row.documentId,
        body: row.body,
        createdAt: row.createdAt,
        author: row.author?.username ?? null,
      }));
    },

    async getStatus(documentId: string) {
      const row = await comments().findOne({ documentId, fields: ['moderationStatus'] });
      return row ? (commentRow.parse(row).moderationStatus ?? null) : null;
    },
  };
};

export type ModerationService = ReturnType<typeof moderation>;

export default moderation;
