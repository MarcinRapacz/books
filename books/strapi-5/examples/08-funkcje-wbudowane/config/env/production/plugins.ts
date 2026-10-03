import type { Core } from '@strapi/strapi';

// Production stores media in an S3-compatible bucket (MinIO, R2, Hetzner, AWS).
// Requires: npm install @strapi/provider-upload-aws-s3
const config = ({ env }: Core.Config.Shared.ConfigParams): Core.Config.Plugin => ({
  upload: {
    config: {
      provider: 'aws-s3',
      providerOptions: {
        baseUrl: env('S3_PUBLIC_URL'), // e.g. https://media.redakcja.example
        s3Options: {
          credentials: {
            accessKeyId: env('S3_ACCESS_KEY_ID'),
            secretAccessKey: env('S3_ACCESS_SECRET'),
          },
          region: env('S3_REGION', 'auto'),
          endpoint: env('S3_ENDPOINT'), // e.g. https://minio.internal:9000
          forcePathStyle: env.bool('S3_FORCE_PATH_STYLE', true), // MinIO needs it, R2 does not
          params: {
            Bucket: env('S3_BUCKET'),
          },
        },
      },
    },
  },
});

export default config;
