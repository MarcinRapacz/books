// Loaded before article.ts, so /articles/mine is matched before /articles/:id.
export default {
  routes: [
    {
      method: 'GET',
      path: '/articles/mine',
      handler: 'api::article.article.mine',
    },
  ],
};
