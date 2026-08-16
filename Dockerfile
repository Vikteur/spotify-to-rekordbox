# syntax=docker/dockerfile:1
#
# One image, one process: uvicorn serves the API *and* the built React client
# (server/main.py mounts ../dist as static files), so there is nothing else to
# run on the box.

# --- stage 1: build the client -------------------------------------------
FROM node:24-alpine AS web
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json vite.config.ts ./
COPY client/ ./client/
# `npm run build` = tsc --noEmit && vite build -> /build/dist
RUN npm run build

# --- stage 2: runtime -----------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Fixed uid so the named data volume keeps working across image rebuilds.
RUN useradd --system --uid 10001 --create-home --home-dir /home/app app

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/
COPY --from=web /build/dist ./dist

# Docker seeds a fresh named volume from this dir, ownership included, which is
# what lets the non-root user write library.db.
RUN mkdir -p /app/data && chown -R 10001:10001 /app/data

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
