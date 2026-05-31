FROM node:20-alpine AS builder
WORKDIR /app

# Dummy secret for build-time static analysis only.
# The real secret comes from docker-compose env at runtime.
ENV NEXTAUTH_SECRET=build-time-placeholder-not-used-at-runtime

COPY package*.json ./
RUN npm install --legacy-peer-deps --fetch-retries=5 --fetch-retry-mintimeout=10000 --fetch-retry-maxtimeout=60000

COPY . .
RUN npx prisma generate
RUN npm run build

FROM node:20-alpine
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/prisma.config.ts ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/entrypoint.sh ./

RUN chmod +x entrypoint.sh

EXPOSE 3000
CMD ["./entrypoint.sh"]
