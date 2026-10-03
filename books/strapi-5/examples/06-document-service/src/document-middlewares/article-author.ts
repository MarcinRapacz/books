import type { Core, Modules } from '@strapi/strapi';

type AuthState = { auth?: { strategy?: { name?: string } }; user?: { id: number } };

export const articleAuthor = (strapi: Core.Strapi): Modules.Documents.Middleware.Middleware => {
  return async (context, next) => {
    if (context.uid !== 'api::article.article' || context.action !== 'create') return next();

    // Only Content API users are article authors; admin panel users are a different table.
    const state = strapi.requestContext.get()?.state as AuthState | undefined;
    if (state?.auth?.strategy?.name === 'users-permissions' && state.user) {
      const data = context.params.data as Record<string, unknown>;
      data.author = state.user.id;
    }
    return next();
  };
};
