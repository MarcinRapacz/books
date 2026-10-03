import type { Core, Data } from '@strapi/strapi';

/** The users-permissions user that the `authenticate` step stores in `ctx.state.user`. */
export type AuthUser = Data.ContentType<'plugin::users-permissions.user'>;

// Koa types `ctx.state` as `any`; this makes `ctx.state.user` typed in middlewares and controllers.
declare module 'koa' {
  interface DefaultState {
    user?: AuthUser;
  }
}

/**
 * What a policy receives at runtime: a shallow copy of the Koa context.
 * Core.PolicyContext (Strapi 5.56) declares neither `state` nor the router's `params`.
 */
export type PolicyContext = Core.PolicyContext & {
  state: { user?: AuthUser };
  params: Record<string, string | undefined>;
};

/** Core.PolicyHandler returns a plain boolean, but the policy runner awaits the result. */
export type Policy<TConfig = unknown> = (
  policyContext: PolicyContext,
  config: TConfig,
  context: { strapi: Core.Strapi }
) => Promise<boolean | undefined> | boolean | undefined;
