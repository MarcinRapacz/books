import type { Core } from '@strapi/strapi';

// Read by the OpenAPI generator (@strapi/openapi in Strapi 5.56), not described in the docs.
// Without it the spec gets an empty server URL, and its paths (/articles) lack the /api prefix.
export default ({ env }: Core.Config.Shared.ConfigParams) => ({
  servers: [{ url: `${env('PUBLIC_URL', 'http://localhost:1337')}/api`, description: 'Content API' }],
});
