export default {
  routes: [
    {
      method: 'POST',
      path: '/comments/:id/approve',
      handler: 'api::comment.comment.approve',
    },
  ],
};
