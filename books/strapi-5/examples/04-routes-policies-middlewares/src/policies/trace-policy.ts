import type { Core } from '@strapi/strapi';

type TracePolicyContext = Core.PolicyContext & {
  state: { user?: { username: string } };
  params: Record<string, string>;
};

// Learning aid: logs what a policy can see before the controller runs.
export default (
  policyContext: TracePolicyContext,
  _config: unknown,
  { strapi }: { strapi: Core.Strapi }
): boolean => {
  const user = policyContext.state.user?.username ?? 'anonymous';
  strapi.log.info(`[trace] policy: user=${user} params=${JSON.stringify(policyContext.params)}`);
  return true;
};
