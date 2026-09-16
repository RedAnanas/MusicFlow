FROM node:18-alpine AS frontend-build
WORKDIR /frontend
COPY VERSION /VERSION
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ARG APP_VERSION=dev
WORKDIR /app
LABEL org.opencontainers.image.version=$APP_VERSION
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx tini \
    && rm -f /etc/nginx/sites-enabled/default \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY VERSION ./VERSION
COPY --from=frontend-build /frontend/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/start.sh /usr/local/bin/musicflow-start
RUN chmod +x /usr/local/bin/musicflow-start \
    && mkdir -p /data/config /data/logs /data/temp /data/tools/ffmpeg /music
EXPOSE 80
ENTRYPOINT ["tini", "--"]
CMD ["/usr/local/bin/musicflow-start"]
