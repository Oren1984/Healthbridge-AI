# Build context: repository root (shared .dockerignore). Synthetic sample documents are generated
# from app/seed_data.py, so no data files are copied into the image.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS deps
COPY backend/requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM base AS runtime
COPY --from=deps /install /usr/local
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/documents && chown -R app:app /data
COPY --chown=app:app backend/alembic.ini backend/entrypoint.sh /app/
COPY --chown=app:app backend/alembic /app/alembic
COPY --chown=app:app backend/app /app/app
USER app
EXPOSE 8003
HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8003/api/health', timeout=2)"
CMD ["sh", "/app/entrypoint.sh"]

# Test image: runtime + dev dependencies + tests (never deployed).
FROM runtime AS test
USER root
COPY backend/requirements-dev.txt backend/requirements.txt /tmp/
RUN pip install -r /tmp/requirements-dev.txt
COPY --chown=app:app backend/tests /app/tests
COPY --chown=app:app backend/setup.cfg /app/setup.cfg
USER app
CMD ["python", "-m", "pytest", "-q"]
