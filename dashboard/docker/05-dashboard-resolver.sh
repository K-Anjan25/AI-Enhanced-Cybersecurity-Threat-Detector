#!/bin/sh
# Runs in the nginx image's /docker-entrypoint.d/ before the envsubst step.
#
# The resolver is written as its own conf.d file, not substituted into the
# template: the image's env-to-template step did not reliably expand
# ${NGINX_LOCAL_RESOLVERS}, and nginx refused to start with a literal
# "${NGINX_LOCAL_RESOLVERS}" as a hostname. This file is included in the http
# context, so the template's per-request proxy_pass can resolve the backend.
#
# RESOLV_CONF and CONF_DIR exist so the script can be exercised outside the image.
set -eu

RESOLV_CONF="${RESOLV_CONF:-/etc/resolv.conf}"
CONF_DIR="${CONF_DIR:-/etc/nginx/conf.d}"
OUT="$CONF_DIR/00-dashboard-resolver.conf"

servers=$(awk '$1 == "nameserver" { if ($2 ~ /:/) printf "[%s] ", $2; else printf "%s ", $2 }' "$RESOLV_CONF" 2>/dev/null || true)
# Docker's embedded DNS, used when the container has no nameserver of its own.
[ -n "$servers" ] || servers="127.0.0.11 "

servers=${servers% }
printf 'resolver %s valid=10s ipv6=off;\n' "$servers" > "$OUT"
echo "dashboard resolver: $servers"

# The backend hostname. nginx's resolver does not apply the pod's DNS search
# domains, so a short name like `backend` fails inside Kubernetes. When the pod
# is in a cluster (search domain ends in .svc.cluster.local), use the full
# name. Docker Compose keeps the short name, which Docker's DNS resolves.
backend_host=backend
search_domain=$(awk '$1 == "search" { print $2; exit }' "$RESOLV_CONF" 2>/dev/null || true)
case "$search_domain" in
    *.svc.cluster.local) backend_host="backend.$search_domain" ;;
esac

# Defined here, in the http context, so the template's proxy_pass can use it.
# AEGIS_BACKEND_URL, when set, is the full backend URL (for example
# https://aegis-backend.onrender.com). Used where the backend is a public service.
if [ -n "${AEGIS_BACKEND_URL:-}" ]; then
    backend_url="$AEGIS_BACKEND_URL"
else
    backend_url="http://$backend_host:8000"
fi
printf 'map $host $backend_upstream {\n    default %s;\n}\n' "$backend_url" > "$CONF_DIR/01-dashboard-backend.conf"
echo "dashboard backend: $backend_url"
