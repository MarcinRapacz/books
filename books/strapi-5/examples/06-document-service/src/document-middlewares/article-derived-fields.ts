import type { Core, Modules } from '@strapi/strapi';

const WORDS_PER_MINUTE = 200;

type BlockNode = { text?: string; children?: BlockNode[] };
type ContentBlock = { __component: string; body?: unknown };

const countWords = (text: string) => text.split(/\s+/).filter(Boolean).length;

const blockText = (nodes: BlockNode[]): string =>
  nodes.map((node) => `${node.text ?? ''} ${blockText(node.children ?? [])}`).join(' ');

export const readingTimeOf = (content: ContentBlock[]) => {
  const words = content.reduce((sum, block) => {
    if (block.__component === 'shared.rich-text' && Array.isArray(block.body)) {
      return sum + countWords(blockText(block.body as BlockNode[]));
    }
    if (block.__component === 'shared.quote' && typeof block.body === 'string') {
      return sum + countWords(block.body);
    }
    return sum;
  }, 0);
  return Math.max(1, Math.ceil(words / WORDS_PER_MINUTE));
};

export const slugify = (title: string) =>
  title
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/ł/g, 'l')
    .replace(/Ł/g, 'L')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');

const uniqueSlug = async (strapi: Core.Strapi, base: string) => {
  const articles = strapi.documents('api::article.article');
  let slug = base;
  for (let suffix = 2; (await articles.count({ filters: { slug } })) > 0; suffix++) {
    slug = `${base}-${suffix}`;
  }
  return slug;
};

export const articleDerivedFields = (strapi: Core.Strapi): Modules.Documents.Middleware.Middleware => {
  return async (context, next) => {
    if (context.uid !== 'api::article.article') return next();
    if (context.action !== 'create' && context.action !== 'update') return next();

    const data = context.params.data as Record<string, unknown> | undefined;
    if (data) {
      if (Array.isArray(data.content)) {
        data.readingTime = readingTimeOf(data.content as ContentBlock[]);
      }
      if (context.action === 'create' && !data.slug && typeof data.title === 'string') {
        data.slug = await uniqueSlug(strapi, slugify(data.title));
      }
    }
    return next();
  };
};
