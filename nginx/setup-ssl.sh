#!/usr/bin/env bash
# =============================================================================
# setup-ssl.sh — Bootstrap Nginx + Let's Encrypt SSL for avpk.prodit.rs
#
# Run once on the production server as root (or with sudo).
#
# What it does:
#   Step 1 — Deploy HTTP-only nginx config (no SSL paths required)
#   Step 2 — Reload nginx so it passes config test
#   Step 3 — Issue certificate via certbot --nginx
#   Step 4 — Deploy full HTTPS config
#   Step 5 — Final reload and smoke-test
# =============================================================================

set -euo pipefail

DOMAIN="avpk.prodit.rs"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SITES_AVAILABLE="/etc/nginx/sites-available/${DOMAIN}"
SITES_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
EXTRAS_CONF="/etc/nginx/conf.d/avpk-extras.conf"
CERTBOT_WEBROOT="/var/www/certbot"

# Color helpers
info()    { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
success() { echo -e "\033[1;32m[OK]\033[0m    $*"; }
error()   { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || error "Run this script as root or with sudo."
command -v nginx   >/dev/null 2>&1 || error "nginx is not installed."
command -v certbot >/dev/null 2>&1 || error "certbot is not installed (apt install certbot python3-certbot-nginx)."

# ---------------------------------------------------------------------------
# STEP 1 — HTTP-only extras + site config
# ---------------------------------------------------------------------------
info "Step 1: Installing http-context extras (WebSocket map + rate-limit zones)..."
cp "${REPO_DIR}/nginx/http-extras.conf" "${EXTRAS_CONF}"
success "Installed ${EXTRAS_CONF}"

info "Step 1: Installing HTTP-only site config (no SSL paths)..."
mkdir -p "${CERTBOT_WEBROOT}"
cp "${REPO_DIR}/nginx/avpk.prodit.rs.http-only.conf" "${SITES_AVAILABLE}"
ln -sf "${SITES_AVAILABLE}" "${SITES_ENABLED}"
success "Installed ${SITES_AVAILABLE} (HTTP-only)"

# ---------------------------------------------------------------------------
# STEP 2 — Validate and reload nginx
# ---------------------------------------------------------------------------
info "Step 2: Testing nginx config..."
nginx -t || error "nginx -t failed — fix config errors before continuing."
success "nginx config is valid."

info "Step 2: Reloading nginx..."
systemctl reload nginx
success "nginx reloaded."

# ---------------------------------------------------------------------------
# STEP 3 — Issue certificate
# ---------------------------------------------------------------------------
info "Step 3: Requesting SSL certificate from Let's Encrypt..."
certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos \
    --email "admin@prodit.rs" --redirect \
    || error "certbot failed — check DNS, firewall (port 80), and certbot logs."
success "Certificate issued for ${DOMAIN}."

# ---------------------------------------------------------------------------
# STEP 4 — Deploy full HTTPS config
# ---------------------------------------------------------------------------
info "Step 4: Installing full HTTPS config..."
cp "${REPO_DIR}/nginx/avpk.prodit.rs.conf" "${SITES_AVAILABLE}"
# symlink already exists; cp overwrites the target file in sites-available
success "Installed ${SITES_AVAILABLE} (HTTPS)"

# ---------------------------------------------------------------------------
# STEP 5 — Final validate, reload, smoke-test
# ---------------------------------------------------------------------------
info "Step 5: Testing full HTTPS nginx config..."
nginx -t || error "nginx -t failed after deploying HTTPS config."
success "nginx config is valid."

info "Step 5: Reloading nginx..."
systemctl reload nginx
success "nginx reloaded."

info "Step 5: Smoke-testing endpoints..."
sleep 2

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -L --max-time 10 "http://${DOMAIN}" || true)
HTTPS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://${DOMAIN}" || true)
API_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://${DOMAIN}/api/health" || true)

echo ""
echo "  http://${DOMAIN}          → HTTP ${HTTP_CODE}"
echo "  https://${DOMAIN}         → HTTP ${HTTPS_CODE}"
echo "  https://${DOMAIN}/api/health → HTTP ${API_CODE}"
echo ""

[[ "$HTTPS_CODE" =~ ^(200|301|302|307|308)$ ]] \
    && success "HTTPS is reachable." \
    || echo -e "\033[1;33m[WARN]\033[0m  HTTPS returned ${HTTPS_CODE} — check backend services."

success "SSL setup complete for ${DOMAIN}."
