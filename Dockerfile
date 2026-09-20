FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.11-slim AS build
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    AUTOPITCH_FRONTEND_DIR=/app/web \
    AUTOPITCH_DB_PATH=/data/autopitch.db
RUN useradd --create-home --uid 10001 app && mkdir /data && chown app /data
COPY --from=build /install /usr/local
COPY --from=web /web/dist /app/web
USER app
WORKDIR /home/app
# Saved reports live here; mount a volume to keep them across restarts.
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "autopitch.api:app", "--host", "0.0.0.0", "--port", "8000"]
