#!/usr/bin/env bash
#
# Run AEGIS on Docker Desktop Kubernetes with one command.
#
#   scripts/k8s-local.sh up     start Postgres (Compose), build the three images,
#                               create the namespace and secret, install the Helm
#                               chart, then forward the dashboard to localhost:8080
#   scripts/k8s-local.sh down   uninstall the chart, delete the namespace, stop Postgres
#
# Development only. The chart runs in development mode with small limits
# (helm/aegis/values-local.yaml). Nothing here touches a real cluster: the kube
# context must be docker-desktop unless AEGIS_K8S_CONTEXT says otherwise.
#
# Generated secrets live outside the repository, in
# ${AEGIS_K8S_LOCAL_STATE:-$HOME/.config/aegis-k8s-local}/secrets.env (mode 600).
# Re-running `up` keeps them, so the database and sign-in survive a restart.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NS="aegis"
RELEASE="aegis"
CONTEXT="${AEGIS_K8S_CONTEXT:-docker-desktop}"
STATE_DIR="${AEGIS_K8S_LOCAL_STATE:-$HOME/.config/aegis-k8s-local}"
ENV_FILE="$STATE_DIR/secrets.env"
COMPOSE_FILE="$ROOT/docker/docker-compose.yml"
ADMIN_EMAIL="admin@aegis.local"
DB_URL="postgresql+psycopg://aegis:aegis@host.docker.internal:5432/aegis" # pragma: allowlist secret

die() {
    echo "error: $*" >&2
    exit 1
}

need() {
    command -v "$1" >/dev/null 2>&1 || die "$1 is not installed. $2"
}

kc() {
    kubectl --context "$CONTEXT" "$@"
}

check_prerequisites() {
    need docker "Install Docker Desktop and start it."
    need kubectl "It ships with Docker Desktop; enable it in Settings > Kubernetes."
    need helm "Install Helm 3.12 or newer."
    docker compose version >/dev/null 2>&1 || die "docker compose is not available."
    if ! kubectl config get-contexts -o name | grep -qx "$CONTEXT"; then
        die "kube context '$CONTEXT' not found. Enable Kubernetes in Docker Desktop, or set AEGIS_K8S_CONTEXT."
    fi
    kc get nodes >/dev/null 2>&1 || die "cannot reach context '$CONTEXT'. Is Kubernetes running in Docker Desktop?"
}

# Random URL-safe token from N bytes. Uses openssl (ships with Git for Windows
# and Linux/macOS) or /dev/urandom, so no Python install is needed.
random_token() {
    local raw
    if command -v openssl >/dev/null 2>&1; then
        raw="$(openssl rand -base64 "$1")"
    else
        raw="$(head -c "$1" /dev/urandom | base64)"
    fi
    printf '%s' "$raw" | tr -d '\n+/='
}

# Create the secrets file once. Values are written without quotes, because
# `kubectl create secret --from-env-file` does not strip them.
ensure_secrets() {
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"
    if [ -f "$ENV_FILE" ]; then
        return
    fi
    local key pass
    key="$(random_token 48)"
    pass="$(random_token 18)"
    (
        umask 077
        {
            echo "AEGIS_SECRET_KEY=$key"
            echo "AEGIS_DATABASE_URL=$DB_URL"
            echo "AEGIS_BOOTSTRAP_ADMIN_EMAIL=$ADMIN_EMAIL"
            echo "AEGIS_BOOTSTRAP_ADMIN_PASSWORD=$pass"
        } >"$ENV_FILE"
    )
    echo "Created $ENV_FILE"
    echo "Admin sign-in: $ADMIN_EMAIL  password: $pass"
    echo "(the password is also in that file; it is not printed again)"
}

start_postgres() {
    # Compose needs AEGIS_SECRET_KEY set, even to start one service.
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
    docker compose -f "$COMPOSE_FILE" up -d --wait postgres
}

build_images() {
    docker build -t "aegis-backend:$IMAGE_TAG" --build-context aegis_ml="$ROOT/ml-service" "$ROOT/backend"
    docker build -t "aegis-ml-service:$IMAGE_TAG" "$ROOT/ml-service"
    docker build -t "aegis-dashboard:$IMAGE_TAG" "$ROOT/dashboard"
}

apply_namespace_and_secret() {
    kc create namespace "$NS" --dry-run=client -o yaml | kc apply -f -
    kc -n "$NS" create secret generic aegis-secrets \
        --from-env-file="$ENV_FILE" --dry-run=client -o yaml | kc apply -f -
}

install_chart() {
    helm --kube-context "$CONTEXT" upgrade --install "$RELEASE" "$ROOT/helm/aegis" \
        -n "$NS" -f "$ROOT/helm/aegis/values-local.yaml" \
        --set "backend.image.tag=$IMAGE_TAG" \
        --set "mlService.image.tag=$IMAGE_TAG" \
        --set "scoringWorker.image.tag=$IMAGE_TAG" \
        --set "dashboard.image.tag=$IMAGE_TAG" \
        --wait --timeout 10m
}

cmd_up() {
    # A new tag for every build. Re-using one tag (0.1.0) let Kubernetes keep
    # running the old image after a rebuild.
    IMAGE_TAG="local-$(date +%Y%m%d%H%M%S)"
    check_prerequisites
    ensure_secrets
    start_postgres
    build_images
    apply_namespace_and_secret
    install_chart
    echo
    echo "AEGIS is running. Open http://localhost:8080 and sign in as $ADMIN_EMAIL."
    echo "The password is in $ENV_FILE. Press Ctrl-C to stop forwarding; the app keeps running."
    kc -n "$NS" port-forward "svc/${RELEASE}-dashboard" 8080:8080
}

cmd_down() {
    check_prerequisites
    helm --kube-context "$CONTEXT" uninstall "$RELEASE" -n "$NS" 2>/dev/null || true
    kc delete namespace "$NS" --ignore-not-found
    if [ -f "$ENV_FILE" ]; then
        set -a
        # shellcheck disable=SC1090
        . "$ENV_FILE"
        set +a
    fi
    docker compose -f "$COMPOSE_FILE" stop postgres
    echo "Stopped. Postgres data is kept in its Compose volume; secrets stay in $STATE_DIR."
}

case "${1:-}" in
    up) cmd_up ;;
    down) cmd_down ;;
    *)
        echo "usage: $0 {up|down}" >&2
        exit 2
        ;;
esac
