export default {
  routes: [
    {
      method: 'GET',
      path: '/articles/:id/related',
      handler: 'api::article.article.related',
    },
  ],
};
