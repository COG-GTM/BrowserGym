# syntax=docker/dockerfile:1.7
# Side runner image: browsergym + Playwright chromium + side_runner (services/runner).
# Build context: repository root.  docker build -f deploy/runner/Dockerfile -t side-runner .
ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright/python:v1.49.1-noble

FROM ${PLAYWRIGHT_IMAGE} AS miniwob
# Pinned to the same commit as `make setup-miniwob`. Set MINIWOB_REF="" to skip.
ARG MINIWOB_REF=7fd85d71a4b60325c6585396ec4f48377d049838
RUN mkdir -p /opt/miniwob-plusplus && if [ -n "$MINIWOB_REF" ]; then \
      curl -fsSL "https://codeload.github.com/Farama-Foundation/miniwob-plusplus/tar.gz/${MINIWOB_REF}" \
      | tar -xz -C /opt/miniwob-plusplus --strip-components=1 --wildcards '*/miniwob/html'; \
    fi

FROM ${PLAYWRIGHT_IMAGE} AS runner
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_BREAK_SYSTEM_PACKAGES=1

# BrowserGym from this repo (not PyPI), so library changes on side/main ship in the image.
ARG BROWSERGYM_PACKAGES="core experiments miniwob"
COPY browsergym/ /opt/side/src/browsergym/
RUN set -eux; pkgs=""; for p in $BROWSERGYM_PACKAGES; do pkgs="$pkgs /opt/side/src/browsergym/$p"; done; \
    pip install --no-cache-dir $pkgs

# browsergym pins its own playwright version: install the matching chromium build (OS deps
# come from the base image) and drop the browsers we don't use.
COPY deploy/scripts/ /opt/side/bin/
RUN set -eux; rm -rf /ms-playwright/firefox-* /ms-playwright/webkit-*; \
    playwright install chromium; \
    keep="$(python -c 'from playwright.sync_api import sync_playwright as s; p=s().start(); print(p.chromium.executable_path.split("/")[2]); p.stop()')"; \
    for d in /ms-playwright/chromium*; do case "$(basename "$d")" in "$keep") ;; *) rm -rf "$d" ;; esac; done; \
    chmod -R a+rX /ms-playwright; ls /ms-playwright

COPY --from=miniwob /opt/miniwob-plusplus /opt/miniwob-plusplus
ENV MINIWOB_URL=file:///opt/miniwob-plusplus/miniwob/html/miniwob/

# services/runner if present in the context, else the deploy stub.
RUN --mount=type=bind,target=/ctx \
    sh /ctx/deploy/scripts/select-src.sh /ctx services/runner deploy/stubs/runner /opt/side/runner && \
    sh /opt/side/bin/pip-install-app.sh /opt/side/runner
ENV PYTHONPATH=/opt/side/runner \
    SIDE_DATA_DIR=/data

RUN mkdir -p /data && chown pwuser:pwuser /data
USER pwuser
WORKDIR /data
VOLUME ["/data"]
CMD ["python", "-m", "side_runner", "--help"]
