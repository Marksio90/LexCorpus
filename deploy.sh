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

read -rp "Email SMTP host (leave empty to skip email auth): " EMAIL_HOST
EMAIL_USER=""
EMAIL_PASS=""
EMAIL_FROM="noreply@${DOMAIN}"
if [[ -n "$EMAIL_HOST" ]]; then
    read -rp "SMTP user: " EMAIL_USER
    read -rsp "SMTP password: " EMAIL_PASS; echo
    read -rp "From address [noreply@${DOMAIN}]: " EMAIL_FROM_INPUT
    EMAIL_FROM="${EMAIL_FROM_INPUT:-$EMAIL_FROM}"
fi

NEXTAUTH_SECRET=$(openssl rand -base64 32)
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
DOMAIN=${DOMAIN}
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_MODEL=sdadas/mmlw-retrieval-roberta-large
RERANK_ENABLED=true
EXPAND_ENABLED=true
QDRANT_COLLECTION=lexcorpus
NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
NEXTAUTH_URL=https://${DOMAIN}
NEXT_PUBLIC_API_URL=https://${DOMAIN}/api
ADMIN_EMAILS=${ADMIN_EMAILS}
EMAIL_SERVER_HOST=${EMAIL_HOST}
EMAIL_SERVER_PORT=587
EMAIL_SERVER_USER=${EMAIL_USER}
EMAIL_SERVER_PASSWORD=${EMAIL_PASS}
EMAIL_FROM=${EMAIL_FROM}
FETCH_YEAR=2024
EOF
chmod 600 .env

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

# ── 9. Summary ────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  LexCorpus deployed successfully!        ${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo ""
echo "  URL:      https://${DOMAIN}"
echo "  Admin:    https://${DOMAIN}/admin"
echo "  API docs: https://${DOMAIN}/api/docs"
echo ""
echo "  Logs:     docker compose logs -f"
echo "  Status:   docker compose ps"
echo "  Restart:  docker compose -f docker-compose.yml -f docker-compose.prod.yml restart"
echo ""
echo "  The ingest pipeline is running in the background."
echo "  First startup may take 20-40 minutes (fetching + embedding 2024 acts)."
echo ""
