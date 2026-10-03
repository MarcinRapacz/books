import type { Core } from '@strapi/strapi';

// Demo only: a policy that always allows the request and logs its position in the chain
const tracePolicy: Core.PolicyHandler = (policyContext, config, { strapi }) => {
  strapi.log.info('[trace]   route policy');
  return true;
};

export default tracePolicy;
