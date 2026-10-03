import type { Core, Modules } from '@strapi/strapi';

const template = {
  subject: 'Nowy komentarz do „<%= article.title %>”',
  text: `Cześć <%= author.username %>,

pod artykułem „<%= article.title %>” pojawił się komentarz czekający na moderację:

<%= comment.body %>`,
  html: `<p>Cześć <%- author.username %>,</p>
<p>pod artykułem <strong><%- article.title %></strong> pojawił się komentarz czekający na moderację:</p>
<blockquote><%- comment.body %></blockquote>`,
};

/**
 * Emails the article's author after a comment has been saved. Registered as a Document Service
 * middleware, so it covers REST, the admin panel and scripts alike (chapter 6).
 */
export const newCommentEmail = (strapi: Core.Strapi): Modules.Documents.Middleware.Middleware => {
  return async (context, next) => {
    const result = await next();
    if (context.uid !== 'api::comment.comment' || context.action !== 'create') return result;

    const { documentId } = result as { documentId: string };
    const comment = await strapi.documents('api::comment.comment').findOne({
      documentId,
      fields: ['body'],
      populate: { article: { fields: ['title'], populate: { author: { fields: ['username', 'email'] } } } },
    });
    const article = comment?.article;
    const author = article?.author;
    if (!comment || !article || !author?.email) return result;

    // Fire and forget: a slow or broken SMTP server must not fail or delay the comment request.
    strapi
      .plugin('email')
      .service('email')
      .sendTemplatedEmail({ to: author.email }, template, {
        comment: { body: comment.body },
        article: { title: article.title },
        author: { username: author.username },
      })
      .catch((error: Error) => strapi.log.error(`New comment email failed: ${error.message}`));

    return result;
  };
};
