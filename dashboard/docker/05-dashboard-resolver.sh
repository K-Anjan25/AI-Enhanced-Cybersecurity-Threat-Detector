#!/bin/sh
# Runs in the nginx image's /docker-entrypoint.d/ before the envsubst step.
#
# The resolver is written as its own conf.d file, not substituted into the
# template: the image's env-to-template step did not reliably expand
# ${NGINX_LOCAL_RESOLVERS}, and nginx refused to start with a literal
# "${NGINX_LOCAL_RESOLVERS}" as a hostname. This file is included in the http
# context, so the template's per-request proxy_pass can resolve `backend`.
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
