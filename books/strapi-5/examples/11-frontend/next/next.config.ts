import type { NextConfig } from 'next';

const strapiUrl = new URL(process.env.STRAPI_URL ?? 'http://localhost:1337');

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: strapiUrl.protocol === 'https:' ? 'https' : 'http',
        hostname: strapiUrl.hostname,
        port: strapiUrl.port,
        pathname: '/uploads/**',
      },
    ],
    // Next 16 refuses to optimize images from localhost and private networks (SSRF protection).
    // Strapi on localhost or in the same Docker network needs this; a public Strapi URL does not.
    dangerouslyAllowLocalIP: process.env.STRAPI_IMAGES_LOCAL === 'true',
  },
};

export default nextConfig;
