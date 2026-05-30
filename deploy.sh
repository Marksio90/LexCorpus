#!/usr/bin/env bash
# deploy.sh — One-shot VPS deployment for LexCorpus
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/YOUR/REPO/main/deploy.sh | bash
#   OR clone the repo and run: bash deploy.sh
#
# Tested on: Ubuntu 22.04 / 24.04

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 1. Collect config ──────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════╗"
echo "║      LexCorpus — Deployment          ║"
echo "╚══════════════════════════════════════╝"
echo ""

read -rp "Domain (e.g. lexcorpus.example.com): " DOMAIN
[[ -z "$DOMAIN" ]] && error "Domain is required"

read -rp "Email for Let's Encrypt notifications: " LE_EMAIL
[[ -z "$LE_EMAIL" ]] && error "Email is required"

read -rp "OpenAI API key: " OPENAI_API_KEY
[[ -z "$OPENAI_API_KEY" ]] && warn "No OpenAI key — LLM generation will fail at runtime"

read -rp "Admin emails (comma-separated, leave empty to allow all): " ADMIN_EMAILS

read -rp "Email SMTP host (e.g. smtp.resend.com — REQUIRED for magic link auth): " EMAIL_HOST
EMAIL_USER=""
EMAIL_PASS=""
EMAIL_FROM="noreply@${DOMAIN}"
if [[ -n "$EMAIL_HOST" ]]; then
    read -rp "SMTP user: " EMAIL_USER
    read -rsp "SMTP password: " EMAIL_PASS; echo
    read -rp "From address [noreply@${DOMAIN}]: " EMAIL_FROM_INPUT
    EMAIL_FROM="${EMAIL_FROM_INPUT:-$EMAIL_FROM}"
else
    warn "No SMTP configured — users CANNOT log in without email delivery!"
fi

echo ""
info "Stripe configuration (for paid plans — skip if not needed yet)"
read -rp "Stripe Secret Key (sk_live_... or sk_test_...): " STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET=""
STRIPE_PRICE_PRO=""
STRIPE_PRICE_KANCELARIA=""
if [[ -n "$STRIPE_SECRET_KEY" ]]; then
    read -rp "Stripe Webhook Secret (whsec_...): " STRIPE_WEBHOOK_SECRET
    read -rp "Stripe Price ID — Pro (price_...): " STRIPE_PRICE_PRO
    read -rp "Stripe Price ID — Kancelaria (price_...): " STRIPE_PRICE_KANCELARIA
fi

# Generate all secrets
NEXTAUTH_SECRET=$(openssl rand -base64 32)
INTERNAL_API_SECRET=$(openssl rand -hex 32)
NEWSLETTER_SECRET=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 20)
REDIS_PASSWORD=$(openssl rand -hex 16)
REPO_DIR="/opt/lexcorpus"

# ── 2. System dependencies ─────────────────────────────────────────────────────
info "Updating system packages…"
apt-get update -qq
apt-get install -y -qq curl git certbot

info "Installing Docker…"
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
else
    info "Docker already installed, skipping"
fi

# ── 3. Clone / update repo ─────────────────────────────────────────────────────
if [[ -d "$REPO_DIR/.git" ]]; then
    info "Updating existing repo at $REPO_DIR…"
    git -C "$REPO_DIR" pull
else
    info "Cloning repo to $REPO_DIR…"
    git clone https://github.com/Marksio90/LexCorpus.git "$REPO_DIR"
fi

cd "$REPO_DIR"

# ── 4. Write .env ──────────────────────────────────────────────────────────────
info "Writing .env…"
if [[ -f .env ]]; then
    warn ".env already exists — backing up to .env.bak and regenerating…"
    cp .env .env.bak
fi
cat > .env <<EOF
# Domain
DOMAIN=${DOMAIN}

# OpenAI
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_MODEL=gpt-4o-mini

# Embeddings (GPU-quality Polish model)
EMBEDDING_MODEL=sdadas/mmlw-retrieval-roberta-large
RERANK_ENABLED=true
RERANK_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
EXPAND_ENABLED=true
HYDE_ENABLED=true

# Data pipeline — ISAP
FETCH_YEAR_FROM=2020
FETCH_YEAR_TO=2025
# SAOS (court decisions)
SAOS_ENABLED=true
SAOS_YEAR_FROM=2020
SAOS_YEAR_TO=2025
# EUR-Lex
EURLEX_ENABLED=true
EURLEX_YEAR_FROM=2020
EURLEX_YEAR_TO=2025
EURLEX_MAX_ACTS=5000
# KIS
KIS_ENABLED=true
KIS_YEAR_FROM=2020
KIS_YEAR_TO=2025

# Qdrant
QDRANT_COLLECTION=lexcorpus

# PostgreSQL
POSTGRES_USER=lexcorpus
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=lexcorpus
DATABASE_URL=postgresql://lexcorpus:${POSTGRES_PASSWORD}@postgres:5432/lexcorpus

# Redis
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
REDIS_PASSWORD=${REDIS_PASSWORD}

# Internal secrets (auto-generated)
INTERNAL_API_SECRET=${INTERNAL_API_SECRET}
NEWSLETTER_INTERNAL_SECRET=${NEWSLETTER_SECRET}
BACKEND_URL=http://api:8000

# NextAuth
NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
NEXTAUTH_URL=https://${DOMAIN}
NEXT_PUBLIC_API_URL=https://${DOMAIN}/api

# Admin
ADMIN_EMAILS=${ADMIN_EMAILS}

# Email (SMTP)
EMAIL_SERVER_HOST=${EMAIL_HOST}
EMAIL_SERVER_PORT=587
EMAIL_SERVER_USER=${EMAIL_USER}
EMAIL_SERVER_PASSWORD=${EMAIL_PASS}
EMAIL_FROM=${EMAIL_FROM}

# Stripe
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}
STRIPE_PRICE_PRO=${STRIPE_PRICE_PRO}
STRIPE_PRICE_KANCELARIA=${STRIPE_PRICE_KANCELARIA}

# Rate limiting
RATE_LIMIT_REQUESTS=20
RATE_LIMIT_WINDOW=60

# CORS (production domain only)
ALLOWED_ORIGINS=https://${DOMAIN}

# Auto-sync
SYNC_ENABLED=true
SYNC_CRON=0 3 * * 0
SYNC_SINCE_DAYS=8
NEWSLETTER_CRON=0 8 * * 1
EOF
chmod 600 .env
info ".env written (permissions: 600)"

# ── 5. Patch nginx config with actual domain ────────────────────────────────────
info "Configuring nginx for domain: $DOMAIN…"
sed -i "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" nginx/nginx.conf

# ── 6. Obtain SSL certificate (HTTP challenge needs port 80 free) ───────────────
info "Obtaining Let's Encrypt certificate for $DOMAIN…"
mkdir -p /var/www/certbot

# Temporarily start nginx on port 80 only (no SSL yet) for ACME challenge
docker run --rm -d --name certbot-nginx \
    -p 80:80 \
    -v /var/www/certbot:/var/www/certbot \
    -v "${REPO_DIR}/nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
    nginx:alpine 2>/dev/null || true

sleep 2

certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --non-interactive \
    --agree-tos \
    --email "$LE_EMAIL" \
    -d "$DOMAIN" || warn "Certbot failed — you may need to run it manually. Continuing anyway."

docker stop certbot-nginx 2>/dev/null || true

# ── 7. Start stack ─────────────────────────────────────────────────────────────
info "Starting LexCorpus stack…"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# ── 8. Set up auto-renew cron ──────────────────────────────────────────────────
info "Setting up certificate auto-renewal…"
CRON_JOB="0 3 * * * certbot renew --quiet --webroot --webroot-path /var/www/certbot && docker exec lexcorpus-nginx nginx -s reload"
(crontab -l 2>/dev/null | grep -v certbot; echo "$CRON_JOB") | crontab -

# ── 9. Set up nightly backups ─────────────────────────────────────────────────
info "Setting up nightly backup cron…"
BACKUP_JOB="0 2 * * * cd ${REPO_DIR} && bash scripts/backup.sh >> /var/log/lexcorpus-backup.log 2>&1"
(crontab -l 2>/dev/null | grep -v "lexcorpus-backup"; echo "$BACKUP_JOB") | crontab -

# ── 10. Summary ───────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   LexCorpus deployed successfully! ✓    ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}URL:${NC}       https://${DOMAIN}"
echo -e "  ${GREEN}Admin:${NC}     https://${DOMAIN}/admin"
echo -e "  ${GREEN}API docs:${NC}  https://${DOMAIN}/api/docs"
echo ""
echo -e "  ${YELLOW}Logi:${NC}      docker compose logs -f"
echo -e "  ${YELLOW}Status:${NC}    docker compose ps"
echo -e "  ${YELLOW}Restart:${NC}   docker compose -f docker-compose.yml -f docker-compose.prod.yml restart"
echo -e "  ${YELLOW}Backup:${NC}    bash scripts/backup.sh"
echo ""

if [[ -z "$STRIPE_SECRET_KEY" ]]; then
    echo -e "  ${YELLOW}⚠  Stripe nie skonfigurowany.${NC} Płatności będą niedostępne."
    echo -e "     Dodaj klucze do .env i uruchom: docker compose restart frontend"
fi

if [[ -z "$EMAIL_HOST" ]]; then
    echo -e "  ${RED}✗  SMTP nie skonfigurowany!${NC} Użytkownicy NIE mogą się zalogować."
    echo -e "     Dodaj EMAIL_SERVER_* do .env i uruchom: docker compose restart frontend"
fi

echo ""
echo -e "  ${GREEN}⚙  Następne kroki:${NC}"
echo -e "     1. Skonfiguruj webhook Stripe: stripe listen --forward-to https://${DOMAIN}/api/stripe/webhook"
echo -e "     2. Monitorowanie uptime: https://uptimerobot.com → monitor https://${DOMAIN}/api/health"
echo -e "     3. Pierwszy ingest może zająć 30-60 min — sprawdź: docker compose logs -f ingest"
echo ""
