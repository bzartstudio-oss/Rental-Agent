#!/usr/bin/env bash
# Container startup sequence — see docs/45_Deployment_Guide.md "Production
# Startup". Fails fast on a missing required setting rather than starting a
# misconfigured server; applies migrations and health-checks before serving.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${WEB_SECRET_KEY:-}" ]; then
    echo "FATAL: WEB_SECRET_KEY is not set." >&2
    echo "A container filesystem is not guaranteed to persist the auto-generated" >&2
    echo "data/.web_secret_key file across restarts/redeploys, which would silently" >&2
    echo "invalidate every session and CSRF token on every restart. Set WEB_SECRET_KEY" >&2
    echo "explicitly (see .env.example / docs/45_Deployment_Guide.md)." >&2
    exit 1
fi

echo "Applying database schema/migrations..."
python -c "from src.storage.database import Database; Database()"

echo "Running health check..."
python scripts/health_check.py || echo "WARNING: health check reported at least one failure — see above. Continuing startup; review before relying on this deployment."

echo "Starting production server..."
exec python -m src.web.wsgi
