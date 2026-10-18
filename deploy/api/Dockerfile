# syntax=docker/dockerfile:1.7
# Side API image: apps/api + side_runner + browsergym + chromium in one image, because the API
# spawns `python -m side_runner ...` as a subprocess per run (docs/side/ARCHITECTURE.md).
# Build context: repository root.  docker build -f deploy/api/Dockerfile -t side-api .
# The runner layers mirror deploy/runner/Dockerfile so BuildKit reuses them across both images.
ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright/python:v1.49.1-noble

FROM ${PLAYWRIGHT_IMAGE} AS miniwob
ARG MINIWOB_REF=7fd85d71a4b60325c6585396ec4f48377d049838
RUN mkdir -p /opt/miniwob-plusplus && if [ -n "$MINIWOB_REF" ]; then \
      curl -fsSL "https://codeload.github.com/Farama-Foundation/miniwob-plusplus/tar.gz/${MINIWOB_REF}" \
      | tar -xz -C /opt/miniwob-plusplus --strip-components=1 --wildcards '*/miniwob/html'; \
    fi

FROM ${PLAYWRIGHT_IMAGE} AS api
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_BREAK_SYSTEM_PACKAGES=1

ARG BROWSERGYM_PACKAGES="core experiments miniwob"
COPY browsergym/ /opt/side/src/browsergym/
RUN set -eux; pkgs=""; for p in $BROWSERGYM_PACKAGES; do pkgs="$pkgs /opt/side/src/browsergym/$p"; done; \
    pip install --no-cache-dir $pkgs

COPY deploy/scripts/ /opt/side/bin/
RUN set -eux; rm -rf /ms-playwright/firefox-* /ms-playwright/webkit-*; \
    playwright install chromium; \
    keep="$(python -c 'from playwright.sync_api import sync_playwright as s; p=s().start(); print(p.chromium.executable_path.split("/")[2]); p.stop()')"; \
    for d in /ms-playwright/chromium*; do case "$(basename "$d")" in "$keep") ;; *) rm -rf "$d" ;; esac; done; \
    chmod -R a+rX /ms-playwright; ls /ms-playwright

COPY --from=miniwob /opt/miniwob-plusplus /opt/miniwob-plusplus
ENV MINIWOB_URL=file:///opt/miniwob-plusplus/miniwob/html/miniwob/

RUN --mount=type=bind,target=/ctx \
    sh /ctx/deploy/scripts/select-src.sh /ctx services/runner deploy/stubs/runner /opt/side/runner && \
    sh /opt/side/bin/pip-install-app.sh /opt/side/runner

# apps/api if present in the context, else the deploy stub.
RUN --mount=type=bind,target=/ctx \
    sh /ctx/deploy/scripts/select-src.sh /ctx apps/api deploy/stubs/api /opt/side/api && \
    sh /opt/side/bin/pip-install-app.sh /opt/side/api && \
    (python -c "import uvicorn" 2>/dev/null || pip install --no-cache-dir "uvicorn[standard]>=0.29,<1")

ENV PYTHONPATH=/opt/side/api:/opt/side/runner \
    SIDE_DATA_DIR=/data \
    PORT=8000
RUN mkdir -p /data && chown pwuser:pwuser /data
USER pwuser
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "/opt/side/bin/healthcheck.py", "http://127.0.0.1:8000/api/v1/health"]
# SIDE_API_APP=<module:attr> overrides the auto-detected ASGI app.
CMD ["python", "/opt/side/bin/serve.py", "--env-var", "SIDE_API_APP", \
     "side_api.main:app", "side_api.app:app", "api.main:app", "app.main:app", "main:app"]
