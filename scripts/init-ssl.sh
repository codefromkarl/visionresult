#!/bin/bash
# SSL Certificate Initialization Script for Let's Encrypt
# Usage: ./scripts/init-ssl.sh your-domain.com your-email@example.com

set -e

DOMAIN=${1:-"imagerecognition.codefromkarl.xyz"}
EMAIL=${2:-"admin@codefromkarl.xyz"}

echo "🔒 Initializing SSL certificates for ${DOMAIN}"

# Create directories
mkdir -p certbot/conf certbot/www

# Check if certificates already exist
if [ -f "certbot/conf/live/${DOMAIN}/fullchain.pem" ]; then
    echo "✅ Certificates already exist for ${DOMAIN}"
    echo "   To renew, run: docker compose run certbot renew"
    exit 0
fi

echo "📋 Requesting new certificates from Let's Encrypt..."

# Use certbot standalone mode for initial certificate
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    -d "${DOMAIN}"

if [ $? -eq 0 ]; then
    echo "✅ SSL certificates obtained successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Update docker-compose.prod.yml to use nginx.conf.prod"
    echo "2. Start the production environment:"
    echo "   docker compose -f docker-compose.prod.yml up -d"
    echo ""
    echo "Certificates will auto-renew via the certbot service."
else
    echo "❌ Failed to obtain certificates"
    echo ""
    echo "Troubleshooting:"
    echo "1. Ensure port 80 is accessible from the internet"
    echo "2. Ensure DNS A record points to this server"
    echo "3. Check firewall settings"
    exit 1
fi
