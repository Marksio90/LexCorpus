#!/bin/sh
set -e

echo "[entrypoint] Running migrations..."
npx prisma migrate deploy

echo "[entrypoint] Starting Next.js..."
exec node server.js
