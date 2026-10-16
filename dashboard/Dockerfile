# AEGIS dashboard: build the static bundle, serve it with nginx.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# nginx-unprivileged runs as uid 101 and listens on 8080, so the container never
# needs root. Plain nginx:alpine would run as root to bind port 80.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
# The image renders /etc/nginx/templates/*.template into conf.d at start.
# 05 writes the resolver directive that the template relies on (see the script).
# Windows checkouts can turn the script's line endings into CRLF, which makes the
# shebang `/bin/sh\r` and the entrypoint fails with "not found". Strip CRs at build time.
USER root
COPY --chmod=0755 docker/05-dashboard-resolver.sh /docker-entrypoint.d/05-dashboard-resolver.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/05-dashboard-resolver.sh
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
USER 101
EXPOSE 8080
