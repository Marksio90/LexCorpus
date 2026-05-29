#!/bin/sh
# Run DB migrations then start Next.js
set -e

# Apply any pending migrations (creates DB file if it doesn't exist)
npx prisma migrate deploy 2>/dev/null || npx prisma db push --accept-data-loss 2>/dev/null || true

exec node server.js
