import type { Core } from '@strapi/strapi';
import { errors } from '@strapi/utils';

// One policy for both APIs: REST passes the Koa context, GraphQL a context with resolver `args`.
type DraftPolicyContext = Core.PolicyContext & {
  request: { query: { status?: string } };
  args?: { status?: string };
  state: { user?: { id: number }; auth?: { strategy?: { name: string } } };
};

// Drafts are readable only by logged-in users and API tokens (e.g. a frontend preview);
// anonymous visitors with the public `find` permission get published content only.
export default (policyContext: DraftPolicyContext) => {
  const requested = policyContext.is('graphql') ? policyContext.args?.status : policyContext.request.query.status;
  if (String(requested ?? '').toLowerCase() !== 'draft') return true;

  const { user, auth } = policyContext.state;
  if (user || auth?.strategy?.name === 'api-token') return true;

  throw new errors.PolicyError('Drafts require authentication');
};
