import type { ComponentType } from 'react';
import type { StrapiApp } from '@strapi/strapi/admin';
import type { ContentManagerPlugin } from '@strapi/content-manager/strapi-admin';
import { Discuss, Search } from '@strapi/icons';
import logo from './extensions/logo.svg';
import { CoverReminder } from './extensions/cover-reminder';
import { OpenOnSiteAction } from './extensions/open-on-site-action';

const seoFields = [
  { name: 'seo-title', type: 'string', label: 'Tytuł SEO z licznikiem' },
  { name: 'seo-description', type: 'text', label: 'Opis SEO z licznikiem' },
] as const;

export default {
  config: {
    locales: ['pl'],
    translations: {
      pl: {
        'Auth.form.welcome.title': 'Witaj w Redakcji',
        'Auth.form.welcome.subtitle': 'Zaloguj się do panelu magazynu',
        'app.components.LeftMenu.navbrand.title': 'Redakcja',
      },
      en: {
        'Auth.form.welcome.title': 'Welcome to Redakcja',
        'app.components.LeftMenu.navbrand.title': 'Redakcja',
      },
    },
    auth: { logo },
    menu: { logo },
    theme: {
      light: {
        colors: {
          primary100: '#fdf0ef',
          primary200: '#f6cfcc',
          primary500: '#d9534c',
          primary600: '#b4231f',
          primary700: '#8f1a17',
        },
      },
      dark: {
        colors: {
          primary100: '#3a1514',
          primary200: '#6b2523',
          primary500: '#e0726c',
          primary600: '#e88a85',
          primary700: '#f2b3af',
        },
      },
    },
    tutorials: false,
    notifications: { releases: false },
  },

  register(app: StrapiApp) {
    for (const field of seoFields) {
      app.customFields.register({
        name: field.name,
        type: field.type,
        icon: Search,
        intlLabel: { id: `redakcja.${field.name}.label`, defaultMessage: field.label },
        intlDescription: { id: `redakcja.${field.name}.description`, defaultMessage: 'Pole z licznikiem znaków' },
        components: {
          Input: async () => {
            const { default: SeoLengthInput } = await import('./extensions/seo-length-input');
            // The registry types Input without props; the Content Manager passes them at runtime.
            return { default: SeoLengthInput as ComponentType };
          },
        },
        options: {
          base: [
            {
              // @ts-expect-error -- the 5.56 type omits the documented `options.*` paths
              name: 'options.recommendedLength',
              type: 'number',
              intlLabel: { id: 'redakcja.seo.recommended', defaultMessage: 'Zalecana długość' },
              description: { id: 'redakcja.seo.recommended.hint', defaultMessage: 'Próg zmiany koloru licznika' },
            },
          ],
        },
      });
    }

    app.widgets.register({
      id: 'pending-comments',
      icon: Discuss,
      title: { id: 'redakcja.widget.pending-comments', defaultMessage: 'Komentarze do moderacji' },
      component: async () => (await import('./extensions/pending-comments-widget')).default,
      link: {
        label: { id: 'redakcja.widget.link', defaultMessage: 'Wszystkie komentarze' },
        href: '/content-manager/collection-types/api::comment.comment',
      },
      permissions: [
        { action: 'plugin::content-manager.explorer.read', subject: 'api::comment.comment' },
      ],
    });
  },

  // bootstrap() receives only a subset of the app (getPlugin, addMenuLink, registerHook...).
  bootstrap(app: Pick<StrapiApp, 'getPlugin'>) {
    const contentManager = app.getPlugin('content-manager');
    // `apis` is typed as unknown on the generic Plugin class.
    const cmApis = contentManager.apis as ContentManagerPlugin['config']['apis'];
    cmApis.addDocumentHeaderAction([OpenOnSiteAction]);
    contentManager.injectComponent('editView', 'right-links', {
      name: 'redakcja-cover-reminder',
      Component: CoverReminder,
    });
  },
};
