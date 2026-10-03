# Chapter 1 – request tracing demo

Copy `config/` and `src/` over the foundation project (`books/strapi-5/code/`). No extra packages.
`src/policies/trace-policy.ts` and the `config` block in `src/api/article/routes/article.ts` are demo-only; drop them before chapter 4.

Check:

    PORT=1301 npx strapi develop --no-watch-admin --no-build-admin
    curl -sg 'localhost:1301/api/articles?fields[0]=title'   # watch the [trace] lines in the server log
    npx strapi routes:list && npx strapi middlewares:list && npx strapi policies:list

`TRACE_SLOW_MS` (default 200) sets the threshold above which a request is logged as `warn`.
