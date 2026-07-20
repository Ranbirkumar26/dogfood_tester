# Website AI Agent container image.
#
# Based on Microsoft's Playwright Python image, which ships Chromium and every OS library the
# browser needs already installed and version-matched to the Playwright wheel. Building on it
# avoids a fragile apt dependency list and a separate browser download at build time.
#
# The image runs headless by default (WA_BROWSER__HEADLESS=true) and as a non-root user. The
# reports directory is a declared volume so run artifacts survive container restarts.

# Pin to a specific Playwright release; keep this in step with the playwright version installed
# by pip below so the bundled browser matches the wheel.
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

# Fail fast and keep Python output unbuffered for container logs.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WA_BROWSER__HEADLESS=true \
    WA_PATHS__REPORTS_DIR=/data/reports \
    WA_PATHS__CHECKPOINT_DB=/data/reports/checkpoints.sqlite3

WORKDIR /app

# Install dependencies first, in their own layer, so code changes do not re-resolve deps.
# Copy only the metadata needed to resolve and build the wheel.
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir . \
    # Ensure the Chromium build matches the installed playwright wheel (no-op if the base
    # image already ships the right one; a safety net against version drift).
    && playwright install chromium

# The base image provides the 'pwuser' non-root account with the browser cache in its home.
# Own the app and data directories, then drop privileges.
RUN mkdir -p /data/reports && chown -R pwuser:pwuser /app /data
USER pwuser

# Persist run artifacts and the checkpoint database across container restarts.
VOLUME ["/data/reports"]

# API server port (only relevant for the api entrypoint).
EXPOSE 8000

# Default to the CLI so `docker run <image> run <url>` works. Override the command to serve the
# API: `docker run <image>` with `command: python -m website_agent.api` (see docker-compose.yml).
ENTRYPOINT ["website-agent"]
CMD ["--help"]
