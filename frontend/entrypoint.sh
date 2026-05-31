#!/bin/sh
set -e

echo "[entrypoint] Running migrations..."
./node_modules/prisma/dist/cli.js migrate deploy

echo "[entrypoint] Starting Next.js..."
exec node server.js
