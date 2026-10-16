#!/bin/sh
set -e
echo "Applying database migrations..."
alembic upgrade head
if [ "${HB_SEED_ON_START:-true}" = "true" ]; then
  python -m app.services.seed seed-if-empty "${HB_SEED_SCENARIO:-showcase}"
fi
# The backend is reachable only through the frontend proxy on the internal network,
# so forwarded headers from that proxy are trusted for client IPs (rate limiting, audit).
exec uvicorn app.main:app --host 0.0.0.0 --port 8003 --proxy-headers --forwarded-allow-ips "*" --no-server-header
