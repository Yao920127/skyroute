# syntax=docker/dockerfile:1

# ---------- build：用 uv 安裝鎖定版本的依賴到虛擬環境 ----------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
# 不使用 BuildKit cache mount：Railway 要求 cache id 帶服務前綴，為了本機與雲端共用同一份 Dockerfile 而省略
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app

# ---------- runtime：只帶虛擬環境與程式碼，非 root 執行 ----------
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" PORT=8000 WEB_CONCURRENCY=2
WORKDIR /app
RUN useradd --system --uid 10001 skyroute
COPY --from=build --chown=skyroute /app /app
USER skyroute
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health')"
# 監聽 ::（Linux 上同時涵蓋 IPv4／IPv6），Railway 私有網路走 IPv6；PORT 由平台或上方預設值提供
CMD ["sh", "-c", "exec uvicorn app.main:app_factory --factory --host :: --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*'"]
