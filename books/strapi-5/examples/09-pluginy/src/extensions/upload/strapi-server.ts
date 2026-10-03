import type { Core } from '@strapi/strapi';

type RouteConfig = { middlewares?: Array<string | Core.MiddlewareHandler> };
type Route = { method: string; path: string; config?: RouteConfig };
type UploadPlugin = { routes: { 'content-api': { routes: Route[] } } };

const MAX_FILES = 3;

// Runs after authorization and body parsing, before the upload controller.
const limitFiles: Core.MiddlewareHandler = async (ctx, next) => {
  const files = ctx.request.files?.files;
  const count = Array.isArray(files) ? files.length : files ? 1 : 0;
  if (count > MAX_FILES) {
    return ctx.badRequest(`Upload at most ${MAX_FILES} files at once`, { count });
  }
  await next();
};

export default (plugin: UploadPlugin) => {
  const uploadRoute = plugin.routes['content-api'].routes.find(
    (route) => route.method === 'POST' && route.path === '/'
  );
  // Internal structure of a built-in plugin: fail loudly after an upgrade instead of silently.
  if (!uploadRoute) {
    throw new Error('upload extension: content-api route POST / not found');
  }
  uploadRoute.config = {
    ...uploadRoute.config,
    middlewares: [...(uploadRoute.config?.middlewares ?? []), limitFiles],
  };
  return plugin;
};
