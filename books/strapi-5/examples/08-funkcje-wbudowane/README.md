# Chapter 8 – built-in features

1. Copy `config/` and `src/` over the foundation project (`books/strapi-5/code/`); `schema.json` enables i18n on articles.
2. `npm install @strapi/provider-email-nodemailer` (and `@strapi/provider-upload-aws-s3` only if you use `config/env/production/plugins.ts`).
3. Reset data: `rm -f .tmp/data.db && npm run seed`. Bootstrap adds the `pl` locale, the upload permission for Authenticated and, when `FRONTEND_WEBHOOK_URL` is set, the `frontend-revalidate` webhook.
4. Helpers live outside the project: `node tools/smtp-sink.mjs 2588` and `WEBHOOK_SECRET=local-test-secret node tools/webhook-receiver.mjs 4808`.
5. Start: `PORT=1308 SMTP_PORT=2588 WEBHOOK_SECRET=local-test-secret FRONTEND_WEBHOOK_URL=http://localhost:4808/api/revalidate CRON_ENABLED=true COMMENT_REJECT_RULE='*/15 * * * * *' node_modules/.bin/strapi develop --no-watch-admin --no-build-admin`.
6. Check: `PUT /api/articles/:documentId?locale=pl` creates a translation, `POST /api/upload` as anna returns `formats`, `POST /api/comments` as piotr prints an e-mail in the SMTP sink, every REST publication prints `entry.publish` in the receiver.
