# Running in Docker

The image is built on Microsoft's Playwright Python base, which ships Chromium and its OS libraries pre-installed and version-matched to the Playwright wheel. It runs headless and as a non-root user, and persists run artifacts to a volume.

## Build

```bash
docker build -t website-ai-agent .
```

## Configure

Copy the example environment and set your provider. For zero-cost runs, point at a local model:

```bash
cp .env.example .env
# Hosted (billed): set WA_LLM__API_KEY
# Local (free):    WA_LLM__BASE_URL=http://host.docker.internal:11434/v1  (Ollama on the host)
```

Secrets are read from the environment at runtime; they are never baked into the image (the `.dockerignore` excludes `.env`).

## Run the CLI

```bash
docker run --rm --env-file .env -v wa_reports:/data/reports \
  website-ai-agent run https://example.com --max-steps 40
```

Reports land in the `wa_reports` volume under `/data/reports/<run_id>/output/`.

## Run the API server

```bash
docker compose up api
# Swagger UI at http://localhost:8000/docs
```

Or a one-shot CLI run through Compose:

```bash
docker compose run --rm cli run https://example.com
```

## Notes

- `shm_size` is set to 1GB in Compose so Chromium tabs do not crash under memory pressure; pass `--shm-size=1g` to `docker run` for the same reason.
- The reports volume holds run artifacts and the checkpoint database, so runs survive container restarts and can be resumed.
- Keep the base image tag in `Dockerfile` in step with the `playwright` version so the bundled browser matches the installed wheel; the build also runs `playwright install chromium` as a safety net.
