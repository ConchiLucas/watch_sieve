FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/pip pip install -e ".[snailjob]" "playwright==1.62.0"
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && python -m playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
COPY configs/ ./configs/
COPY scripts/docker-entrypoint.py ./scripts/docker-entrypoint.py
COPY --from=frontend /web/dist ./web/dist
RUN mkdir -p /app/data
ENTRYPOINT ["python", "/app/scripts/docker-entrypoint.py"]
CMD ["web"]
