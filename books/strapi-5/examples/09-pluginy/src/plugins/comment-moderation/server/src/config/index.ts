import { z } from '@strapi/utils';

const configSchema = z.object({
  pageSize: z.number().int().min(1).max(100),
  previewLength: z.number().int().min(20),
});

export type PluginConfig = z.infer<typeof configSchema>;

export default {
  default: { pageSize: 20, previewLength: 200 } satisfies PluginConfig,
  // Runs at startup on the merged config; a throw stops Strapi with the plugin name in the error.
  validator(config: unknown) {
    configSchema.parse(config);
  },
};
