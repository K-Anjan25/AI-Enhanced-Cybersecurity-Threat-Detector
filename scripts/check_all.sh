#!/usr/bin/env bash
#
# Run every check that CI runs, locally, in one command.
#
# Usage:
#   scripts/check_all.sh            # run everything
#   scripts/check_all.sh backend    # run one suite
#
# Exits non-zero on the first failing suite and prints a summary at the end.
# A clean exit is not a pass on its own — read the output (rule R-92).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET="${1:-all}"
FAILED=()
PASSED=()

# Require an activated virtualenv rather than silently installing into the
# system interpreter.
if ! python3 -c 'import pytest' 2>/dev/null; then
    echo "error: pytest is not importable. Activate the project venv first:" >&2
    echo "  python3 -m venv .venv && . .venv/bin/activate" >&2
    echo "  pip install -e 'backend[dev]' -e 'ml-service[dev]'" >&2
    exit 2
fi

run() {
    local name="$1"
    shift
    echo
    echo "── ${name} ─────────────────────────────────────────────"
    if "$@"; then
        PASSED+=("$name")
    else
        FAILED+=("$name")
        echo "FAILED: ${name}" >&2
    fi
}

check_docs() {
    run "docs: lint"        ruff check scripts/
    run "docs: format"      black --check scripts/
    run "scripts: types"    mypy scripts/check_docs.py scripts/check_compose.py
    run "docs: integrity"   python scripts/check_docs.py
}

check_infra() {
    run "infra: compose consistency" python scripts/check_compose.py
}

check_backend() {
    run "backend: lint"           bash -c 'cd backend && ruff check .'
    run "backend: format"         bash -c 'cd backend && black --check .'
    run "backend: types (strict)" bash -c 'cd backend && mypy'
    run "backend: security"       bash -c 'cd backend && bandit -q -r app'
    run "backend: boundaries"     bash -c 'cd backend && lint-imports'
    run "backend: tests"          bash -c 'cd backend && pytest -q --cov=app'
}

check_ml() {
    run "ml-service: lint"        bash -c 'cd ml-service && ruff check .'
    run "ml-service: format"      bash -c 'cd ml-service && black --check .'
    run "ml-service: types"       bash -c 'cd ml-service && mypy'
    run "ml-service: tests"       bash -c 'cd ml-service && pytest -q'
}

check_dashboard() {
    if [ ! -d dashboard/node_modules ]; then
        echo
        echo "── dashboard ───────────────────────────────────────────"
        echo "SKIPPED: dashboard/node_modules missing. Run: (cd dashboard && npm ci)"
        FAILED+=("dashboard: dependencies not installed")
        return
    fi
    run "dashboard: types"   bash -c 'cd dashboard && npm run typecheck --silent'
    run "dashboard: lint"    bash -c 'cd dashboard && npm run lint --silent'
    run "dashboard: tests"   bash -c 'cd dashboard && npm test --silent'
    run "dashboard: build"   bash -c 'cd dashboard && npm run build --silent'
}

case "$TARGET" in
    docs)      check_docs ;;
    infra)     check_infra ;;
    backend)   check_backend ;;
    ml)        check_ml ;;
    dashboard) check_dashboard ;;
    all)       check_docs; check_infra; check_backend; check_ml; check_dashboard ;;
    *) echo "usage: $0 [all|docs|infra|backend|ml|dashboard]" >&2; exit 2 ;;
esac

echo
echo "══════════════════════════════════════════════════════════"
echo "passed: ${#PASSED[@]}   failed: ${#FAILED[@]}"
if [ "${#FAILED[@]}" -gt 0 ]; then
    printf '  FAILED  %s\n' "${FAILED[@]}"
    exit 1
fi
echo "all checks passed"
