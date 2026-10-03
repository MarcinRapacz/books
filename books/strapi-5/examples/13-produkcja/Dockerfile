# syntax=docker/dockerfile:1

# 1. Build: all dependencies (incl. devDependencies), compile TypeScript and the admin panel.
FROM node:22-alpine AS build
WORKDIR /opt/app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# NODE_ENV only after npm ci, otherwise npm skips devDependencies needed by the build.
ENV NODE_ENV=production
# `strapi build` loads the whole config, so the fail-fast checks in config/env/production need values.
# Only the path of PUBLIC_URL reaches the admin bundle; keep it equal to the real one ("/").
RUN PUBLIC_URL=http://build.invalid DATABASE_NAME=build DATABASE_USERNAME=build DATABASE_PASSWORD=build \
    npm run build

# 2. Runtime dependencies only, installed separately so the final image carries no build cache.
FROM node:22-alpine AS deps
WORKDIR /opt/app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

# 3. Runtime: compiled code, production node_modules and the few files Strapi reads at runtime.
FROM node:22-alpine
ENV NODE_ENV=production
WORKDIR /opt/app
COPY --from=deps --chown=node:node /opt/app/node_modules ./node_modules
COPY --from=build --chown=node:node /opt/app/dist ./dist
COPY --chown=node:node package.json package-lock.json tsconfig.json favicon.png ./
# Sources stay in the image: CLI commands (import, export, console) recompile TypeScript before they run.
COPY --chown=node:node config ./config
COPY --chown=node:node src ./src
COPY --chown=node:node types ./types
COPY --chown=node:node database ./database
COPY --chown=node:node public ./public
USER node
EXPOSE 1337
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:1337/_health || exit 1
CMD ["node_modules/.bin/strapi", "start"]
