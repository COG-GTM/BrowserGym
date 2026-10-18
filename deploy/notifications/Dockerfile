# syntax=docker/dockerfile:1.7
# Side notifications image (services/notifications): Expo push on run status changes.
# Build context: repository root.  docker build -f deploy/notifications/Dockerfile -t side-notifications .
ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

COPY deploy/scripts/ /opt/side/bin/
# services/notifications if present in the context, else the deploy stub.
RUN --mount=type=bind,target=/ctx \
    sh /ctx/deploy/scripts/select-src.sh /ctx services/notifications deploy/stubs/notifications /opt/side/notifications && \
    sh /opt/side/bin/pip-install-app.sh /opt/side/notifications && \
    (python -c "import uvicorn" 2>/dev/null || pip install --no-cache-dir "uvicorn[standard]>=0.29,<1")

ENV PYTHONPATH=/opt/side/notifications \
    SIDE_DATA_DIR=/data \
    PORT=8010
# UID/GID 1001 = pwuser in the Playwright-based api/runner images, so whichever container
# initializes the shared side-data volume first, /data stays writable for all of them.
RUN groupadd --gid 1001 side && useradd --create-home --uid 1001 --gid 1001 side \
    && mkdir -p /data && chown 1001:1001 /data
USER side
WORKDIR /data
EXPOSE 8010
# The contract defines no health route for this service: any HTTP answer < 500 on /health = up.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD ["python", "/opt/side/bin/healthcheck.py", "http://127.0.0.1:8010/health", "--any"]
# SIDE_NOTIFICATIONS_APP=<module:attr> overrides the auto-detected ASGI app.
CMD ["python", "/opt/side/bin/serve.py", "--env-var", "SIDE_NOTIFICATIONS_APP", \
     "side_notifications.main:app", "side_notifications.app:app", "notifications.main:app", "app.main:app", "main:app"]
