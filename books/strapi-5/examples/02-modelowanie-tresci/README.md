# Chapter 2 – content modelling

Copy `database/migrations/2026.10.03T12.00.00.rename-article-excerpt-to-lead.js` into the foundation project (`code/`). No extra packages.

Use it only together with the rename: in `src/api/article/content-types/article/schema.json` change `excerpt` to `lead`, then start Strapi once. The migration runs before the schema sync, so existing texts move to `lead` instead of being dropped.

Check: `curl -g 'localhost:1337/api/articles?fields[0]=lead'` returns the original excerpts; the log contains `migrated 2026.10.03T12.00.00...`. Without the migration the same rename silently drops the column.
