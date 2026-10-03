# Chapter 12 – TypeScript, tests and AI tools

Apply on top of the foundation (`code/`) with chapters 4 and 5 already copied (see their READMEs), then copy this directory (except this README) over it, including `.github/` and `tsconfig.json` (adds `vitest.config.mts` to `exclude`).

    npm install -D vitest@4 supertest @types/supertest
    npm pkg set scripts.test="tsc -p . && vitest run"
    npm test            # 3 files, 8 tests; each file boots Strapi on its own .tmp/test-<worker>.db

`src/types/request-context.ts` types policies (`Policy<TConfig>`) and `ctx.state.user`; `is-owner` and `rate-limit` use it.
MCP server: start with `MCP_ENABLED=true`, create an Admin token (Settings > Administration Panel > Admin Tokens), then
`curl -X POST localhost:1337/mcp -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`.
