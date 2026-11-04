# GigScout web app, served by Caddy (HTTPS, security headers, and the reverse proxy to the API).
# Build from the repository root: docker build -f deploy/web.Dockerfile -t gigscout-web .
FROM node:20.19-alpine AS build
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY packages ./packages
COPY apps/web ./apps/web
COPY apps/api/package.json ./apps/api/package.json
RUN pnpm install --frozen-lockfile --filter "@gigscout/web..."
RUN pnpm --filter "@gigscout/web..." build

FROM caddy:2.10-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /repo/apps/web/dist /srv
