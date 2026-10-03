import { getTranslation } from './utils/getTranslation';
import { PLUGIN_ID } from './pluginId';
import { PERMISSIONS } from './permissions';
import { Initializer } from './components/Initializer';
import { PluginIcon } from './components/PluginIcon';

import type { StrapiApp } from '@strapi/strapi/admin';

const plugin: StrapiApp['appPlugins'][string] = {
  register(app) {
    app.addMenuLink({
      to: `plugins/${PLUGIN_ID}`,
      icon: PluginIcon,
      intlLabel: {
        id: `${PLUGIN_ID}.plugin.name`,
        defaultMessage: 'Comment moderation',
      },
      Component: () => import('./pages/App'),
      // Hides the link for roles without the read action; the page itself is protected too.
      permissions: PERMISSIONS.read,
    });

    app.registerPlugin({
      id: PLUGIN_ID,
      initializer: Initializer,
      isReady: false,
      name: PLUGIN_ID,
    });
  },

  registerTrads({ locales }) {
    return Promise.all(
      locales.map(async (locale) => {
        try {
          const { default: data } = (await import(`./translations/${locale}.json`)) as {
            default: Record<string, string>;
          };
          const prefixed: Record<string, string> = {};
          for (const key of Object.keys(data)) {
            prefixed[getTranslation(key)] = data[key];
          }
          return { data: prefixed, locale };
        } catch {
          return { data: {}, locale };
        }
      })
    );
  },
};

export default plugin;
