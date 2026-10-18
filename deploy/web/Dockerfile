# syntax=docker/dockerfile:1.7
# Side web image: apps/web built with Next.js `output: "standalone"`.
# Build context: repository root.  docker build -f deploy/web/Dockerfile -t side-web .
# Supports a JS workspace at the repo root (apps/web + packages/*) with npm, pnpm or yarn.
ARG NODE_IMAGE=node:22-bookworm-slim

FROM ${NODE_IMAGE} AS build
ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_* values are inlined at build time.
ARG NEXT_PUBLIC_SIDE_API_URL=http://localhost:8000/api/v1
ARG NEXT_PUBLIC_SIDE_MOCK=0
ENV NEXT_PUBLIC_SIDE_API_URL=${NEXT_PUBLIC_SIDE_API_URL} \
    NEXT_PUBLIC_SIDE_MOCK=${NEXT_PUBLIC_SIDE_MOCK}
RUN corepack enable
WORKDIR /repo
COPY . .
RUN set -eu; \
    if [ -d apps/web ] && [ -f apps/web/package.json ]; then app=apps/web; else \
      echo "side-deploy: apps/web not found in build context, using stub deploy/stubs/web" >&2; app=deploy/stubs/web; fi; \
    echo "$app" > /tmp/side-source; \
    root=.; \
    if [ "$app" = deploy/stubs/web ] || { [ ! -f pnpm-workspace.yaml ] && ! grep -qs '"workspaces"' package.json; }; then root="$app"; fi; \
    cd "$root"; \
    if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    elif [ -f yarn.lock ]; then yarn install --immutable || yarn install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then npm ci --no-audit --no-fund; \
    else npm install --no-audit --no-fund; fi; \
    cd /repo/"$app"; \
    if [ -f /repo/pnpm-lock.yaml ] && [ "$root" = . ]; then pnpm run build; \
    elif [ -f /repo/yarn.lock ] && [ "$root" = . ]; then yarn run build; \
    else npm run build; fi; \
    test -d .next/standalone || { echo "side-deploy: $app must set output: \"standalone\" in next.config" >&2; exit 1; }; \
    server="$(find .next/standalone -name server.js -not -path '*/node_modules/*' | head -n1)"; \
    rel="$(dirname "${server#.next/standalone/}")"; \
    mkdir -p /out; cp -a .next/standalone/. /out/; \
    mkdir -p "/out/$rel/.next"; cp -a .next/static "/out/$rel/.next/static"; \
    if [ -d public ]; then cp -a public "/out/$rel/public"; fi; \
    echo "$rel" > /out/.side-web-entry; cp /tmp/side-source /out/.side-source; \
    echo "side-deploy: built $app, server at /app/$rel/server.js"

FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /out/ /app/
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"]
CMD ["sh", "-c", "exec node \"/app/$(cat /app/.side-web-entry)/server.js\""]
