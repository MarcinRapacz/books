const canModerate = {
  name: 'admin::hasPermissions',
  config: { actions: ['plugin::comment-moderation.moderate'] },
};
const onlyPending = {
  name: 'plugin::comment-moderation.comment-in-status',
  config: { statuses: ['pending'] },
};

export default () => ({
  type: 'admin' as const,
  routes: [
    {
      method: 'GET' as const,
      path: '/comments/pending',
      handler: 'moderation.pending',
      config: {
        policies: [
          'admin::isAuthenticatedAdmin',
          { name: 'admin::hasPermissions', config: { actions: ['plugin::comment-moderation.read'] } },
        ],
      },
    },
    { method: 'PUT' as const, path: '/comments/:id/approve', handler: 'moderation.approve',
      config: { policies: ['admin::isAuthenticatedAdmin', canModerate, onlyPending] } },
    { method: 'PUT' as const, path: '/comments/:id/reject', handler: 'moderation.reject',
      config: { policies: ['admin::isAuthenticatedAdmin', canModerate, onlyPending] } },
  ],
});
