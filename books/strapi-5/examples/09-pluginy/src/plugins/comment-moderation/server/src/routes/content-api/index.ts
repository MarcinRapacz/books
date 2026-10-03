export default () => ({
  type: 'content-api' as const,
  routes: [
    {
      method: 'GET' as const,
      path: '/articles/:articleId/comments',
      handler: 'comments.findApproved',
    },
    {
      method: 'POST' as const,
      path: '/comments/:id/report',
      handler: 'comments.report',
      config: {
        policies: [
          { name: 'plugin::comment-moderation.comment-in-status', config: { statuses: ['approved'] } },
        ],
      },
    },
  ],
});
