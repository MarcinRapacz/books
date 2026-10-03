import type { Core } from '@strapi/strapi';

/** Adds the Polish locale next to the default English one; idempotent. */
export async function ensurePolishLocale(strapi: Core.Strapi) {
  const locales = strapi.plugin('i18n').service('locales');
  if (!(await locales.findByCode('pl'))) {
    await locales.create({ code: 'pl', name: 'Polish (pl)' });
  }
}
