import type { Core } from '@strapi/strapi';

type Context = Parameters<Core.MiddlewareHandler>[0];
type Action = (ctx: Context) => Promise<void>;
type RoleSummary = { name: string; type: string };

type UsersPermissionsPlugin = {
  contentTypes: { user: { schema: { attributes: Record<string, unknown> } } };
  controllers: { user: Record<string, Action> };
};

export default (plugin: UsersPermissionsPlugin) => {
  // Public profile name; accepted on registration thanks to register.allowedFields.
  plugin.contentTypes.user.schema.attributes.displayName = {
    type: 'string',
    maxLength: 60,
  };

  const originalMe = plugin.controllers.user.me;

  // The frontend needs the role to decide what to show, but `populate=role` is stripped by
  // sanitization unless the role may read roles. Expose only its name and type.
  plugin.controllers.user.me = async (ctx) => {
    await originalMe(ctx);
    const role = (ctx.state.user as { role?: RoleSummary } | undefined)?.role;
    if (ctx.body && role) {
      ctx.body = { ...ctx.body, role: { name: role.name, type: role.type } };
    }
  };

  return plugin;
};
