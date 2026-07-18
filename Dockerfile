# Production image for the Rental Intelligence Platform's web dashboard.
# See docs/45_Deployment_Guide.md.
#
# Does NOT install Playwright's Chromium — the shipped connectors (demo
# fixtures, RentCast's REST API) never launch a browser; only a
# BrowserCollector-based connector would need it. See docs/45's
# "Browser-Based Connectors" section before adding one in production.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x scripts/docker_entrypoint.sh

# Defaults for running inside a container. Override RENTAL_AGENT_DATA_DIR /
# RENTAL_AGENT_OUTPUT_DIR if the platform's persistent volume is mounted
# somewhere other than /data. WEB_SECRET_KEY has no default here — the
# entrypoint refuses to start without one (see docker_entrypoint.sh).
ENV WEB_HOST=0.0.0.0 \
    WEB_ALLOW_NETWORK=1 \
    WEB_PORT=8000 \
    RENTAL_AGENT_DATA_DIR=/data \
    RENTAL_AGENT_OUTPUT_DIR=/data/output

RUN mkdir -p /data/output /data/media /data/raw_pages /data/cache /app/backups && \
    useradd --create-home --uid 1000 appuser && \
    chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

ENTRYPOINT ["scripts/docker_entrypoint.sh"]
