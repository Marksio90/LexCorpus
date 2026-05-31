#!/bin/sh
set -e

echo "[entrypoint] Running migrations..."
node ./node_modules/prisma/build/index.js migrate deploy

echo "[entrypoint] Starting Next.js..."
exec node server.js
