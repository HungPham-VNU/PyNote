FROM node:22-alpine AS deps
WORKDIR /app
RUN corepack enable
COPY apps/web/package.json apps/web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

FROM node:22-alpine AS builder
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web ./
RUN pnpm build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN corepack enable
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts
EXPOSE 3000
CMD ["pnpm", "start"]
