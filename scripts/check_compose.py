#!/usr/bin/env python3
"""Static consistency checks for the Docker Compose stack and Dockerfiles.

Docker is not available in every development environment, so `docker compose up`
cannot always be executed. These checks verify everything about the compose file
that can be verified without a Docker daemon, by comparing it against the real
application code:

  1. The YAML parses and declares the expected services.
  2. Every AEGIS_* variable in the file is a real field on Settings, so a typo
     cannot silently configure nothing (R-19).
  3. AEGIS_SECRET_KEY is interpolated from the environment, never hardcoded (R-50).
  4. Published ports match the defaults the application actually binds.
  5. Every healthcheck URL corresponds to a route the app really serves.
  6. Every Dockerfile CMD references an importable module and app attribute.
  7. Every build context directory exists.
  8. Every PostgreSQL URL in the file, and the application's own default, names a
     driver the backend declares as a dependency (T-323). A DSN whose driver
     nothing installs is a stack that cannot run its migrations.

It does NOT verify that the images build or that the stack starts. Those need a
Docker daemon; see task.md T-005.
"""

from __future__ import annotations

import importlib
import os
import re
import sys
import tomllib
from typing import Any, cast

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE = os.path.join(ROOT, "docker", "docker-compose.yml")
BACKEND_PYPROJECT = os.path.join(ROOT, "backend", "pyproject.toml")

#: Dialect prefix of a PostgreSQL URL, capturing the driver segment: for
#: ``postgresql+psycopg://`` the driver is ``psycopg``, and for a bare
#: ``postgresql://`` it is empty (SQLAlchemy then picks psycopg2, which is also
#: a decision rather than a default).
POSTGRES_URL_RE = re.compile(r"\bpostgresql(?:\+([a-z0-9_]+))?://")

#: Which distribution provides each SQLAlchemy driver name.
DRIVER_PACKAGES = {"psycopg": "psycopg", "psycopg2": "psycopg2", "asyncpg": "asyncpg"}

#: Network capture containers. Their AEGIS_* variables configure the standalone
#: bridge scripts (read from the environment by the entrypoints), not Settings.
CAPTURE_SERVICES = {"capture", "zeek", "suricata", "tshark"}

EXPECTED_SERVICES = {
    "postgres",
    "redis",
    "kafka",
    "elasticsearch",
    "backend",
    "ml-service",
    "dashboard",
} | CAPTURE_SERVICES

# service -> (build context relative to the compose file, published port)
EXPECTED_BUILD = {
    "backend": ("../backend", 8000),
    "ml-service": ("../ml-service", 8001),
    "dashboard": ("../dashboard", 8080),
}

ENV_VAR_RE = re.compile(r"\bAEGIS_[A-Z0-9_]+")


def fail(problems: list[str], message: str) -> None:
    """Record a failure."""
    problems.append(message)


def load_compose() -> dict[str, Any]:
    """Parse the compose file."""
    with open(COMPOSE, encoding="utf-8") as handle:
        return cast(dict[str, Any], yaml.safe_load(handle))


def settings_fields() -> set[str]:
    """Return the environment variable names Settings actually accepts."""
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    from app.core.config import Settings  # noqa: PLC0415 - path set up above

    prefix = str(Settings.model_config.get("env_prefix", ""))
    return {f"{prefix}{name}".upper() for name in Settings.model_fields}


def served_paths(service: str) -> set[str]:
    """Return every route path a service serves, without starting a server.

    Reads the OpenAPI schema rather than ``app.routes``: this FastAPI version
    keeps included routers nested behind an ``_IncludedRouter`` wrapper, so
    walking ``app.routes`` misses every route that came from a router.
    """
    if service == "backend":
        sys.path.insert(0, os.path.join(ROOT, "backend"))
        from app.core.config import Environment, Settings  # noqa: PLC0415
        from app.main import create_app  # noqa: PLC0415

        app = create_app(
            Settings(
                env=Environment.TEST,
                # Throwaway value for static introspection only. It never serves
                # traffic and is not a credential (R-50).
                secret_key="K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu",  # noqa: S106
            )
        )
    elif service == "ml-service":
        sys.path.insert(0, os.path.join(ROOT, "ml-service"))
        from aegis_ml.serving.app import (  # noqa: PLC0415  # type: ignore[import-not-found]
            create_app as create_ml_app,
        )

        app = create_ml_app()
    else:
        raise ValueError(f"no route introspection for service {service!r}")
    return cast(set[str], set(app.openapi()["paths"]))


def check_services(compose: dict[str, Any], problems: list[str]) -> dict[str, Any]:
    """Verify the declared service set."""
    services = cast(dict[str, Any], compose.get("services", {}))
    missing = EXPECTED_SERVICES - set(services)
    if missing:
        fail(problems, f"compose is missing services: {sorted(missing)}")
    extra = set(services) - EXPECTED_SERVICES
    if extra:
        fail(problems, f"compose declares unexpected services: {sorted(extra)}")
    return services


def check_env_vars(services: dict[str, Any], problems: list[str]) -> None:
    """Every AEGIS_* variable on a Settings-backed service must be a real Settings field."""
    known = settings_fields()
    settings_services = {
        name: svc for name, svc in services.items() if name not in CAPTURE_SERVICES
    }
    text = yaml.safe_dump(settings_services)
    used = set(ENV_VAR_RE.findall(text))
    for var in sorted(used):
        if var not in known:
            fail(problems, f"compose sets {var}, which is not a field on Settings")
    if not used:
        fail(problems, "compose sets no AEGIS_* variables at all")


def declared_driver_packages() -> set[str]:
    """The PostgreSQL driver distributions the backend declares, by import name."""
    with open(BACKEND_PYPROJECT, "rb") as handle:
        project = cast(dict[str, Any], tomllib.load(handle)["project"])
    declared: set[str] = set()
    for requirement in cast(list[str], project.get("dependencies", [])):
        # "psycopg[binary]>=3.2" -> "psycopg"
        name = re.split(r"[\[<>=!; ]", requirement.strip(), maxsplit=1)[0].lower()
        if name in DRIVER_PACKAGES.values():
            declared.add(name)
    return declared


def database_urls(services: dict[str, Any]) -> list[str]:
    """Every configured URL: the compose file's, and the application's own default."""
    environment = cast(
        dict[str, Any], services.get("backend", {}).get("environment", {})
    )
    urls = [
        str(value)
        for value in environment.values()
        if isinstance(value, str) and POSTGRES_URL_RE.search(value)
    ]
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    from app.core.config import Settings  # noqa: PLC0415 - path set up above

    default = Settings.model_fields["database_url"].default
    if isinstance(default, str) and POSTGRES_URL_RE.search(default):
        urls.append(default)
    return urls


def check_database_driver(services: dict[str, Any], problems: list[str]) -> None:
    """Every PostgreSQL URL must name a driver the backend declares (T-323)."""
    declared = declared_driver_packages()
    if not declared:
        fail(
            problems,
            "the backend declares no PostgreSQL driver, so no DSN can be opened",
        )
    urls = database_urls(services)
    if not urls:
        fail(problems, "no PostgreSQL URL found in compose or in Settings' default")
        return
    for url in urls:
        match = POSTGRES_URL_RE.search(url)
        driver = match.group(1) if match else None
        if not driver:
            fail(
                problems,
                f"{url} names no driver, so SQLAlchemy would default to psycopg2",
            )
            continue
        package = DRIVER_PACKAGES.get(driver)
        if package is None:
            fail(
                problems,
                f"{url} names driver {driver!r}, which this check does not know",
            )
            continue
        if package not in declared:
            fail(
                problems,
                f"{url} names driver {driver!r}, but backend/pyproject.toml declares "
                f"{sorted(declared) or 'no driver'}: alembic would fail with ModuleNotFoundError",
            )


def check_secret(services: dict[str, Any], problems: list[str]) -> None:
    """AEGIS_SECRET_KEY must be interpolated, never a literal (R-50)."""
    env = services.get("backend", {}).get("environment", {})
    value = env.get("AEGIS_SECRET_KEY")
    if value is None:
        fail(problems, "backend service does not set AEGIS_SECRET_KEY")
        return
    if not str(value).startswith("${"):
        fail(problems, f"AEGIS_SECRET_KEY is hardcoded in compose: {value!r}")
    if ":?" not in str(value):
        fail(
            problems,
            "AEGIS_SECRET_KEY should use ${VAR:?message} so compose refuses to start without it",
        )


def check_ports(services: dict[str, Any], problems: list[str]) -> None:
    """Published container ports must match what the app binds."""
    for service, (_context, expected_port) in EXPECTED_BUILD.items():
        published = services.get(service, {}).get("ports", [])
        targets = {str(entry).split(":")[-1].split("/")[0] for entry in published}
        if str(expected_port) not in targets:
            fail(
                problems,
                f"{service} does not publish container port {expected_port} "
                f"(found {sorted(targets)})",
            )


def check_healthchecks(services: dict[str, Any], problems: list[str]) -> None:
    """Every healthcheck URL must hit a route the app really serves."""
    url_re = re.compile(r"https?://[^/'\"\s]+(:\d+)?(/[^'\"\s)]*)")
    for name in ("backend", "ml-service"):
        routes = served_paths(name)
        healthcheck = services.get(name, {}).get("healthcheck", {})
        test = " ".join(healthcheck.get("test", []))
        found = url_re.findall(test)
        if not found:
            fail(problems, f"{name} has no healthcheck URL")
            continue
        for _host, path in found:
            if path not in routes:
                fail(
                    problems,
                    f"{name} healthcheck targets {path}, which is not a served route",
                )


def check_dockerfiles(problems: list[str]) -> None:
    """Each Dockerfile CMD must reference an importable module and attribute."""
    expectations = {
        "backend/Dockerfile": ("app.main", "app"),
        "ml-service/Dockerfile": ("aegis_ml.serving.app", "app"),
    }
    for relative, (module, attribute) in expectations.items():
        path = os.path.join(ROOT, relative)
        if not os.path.exists(path):
            fail(problems, f"{relative} is missing")
            continue
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        target = f"{module}:{attribute}"
        if target not in content:
            fail(problems, f"{relative} does not serve {target}")
            continue
        sys.path.insert(0, os.path.join(ROOT, os.path.dirname(relative)))
        try:
            imported = importlib.import_module(module)
            target_obj = getattr(imported, attribute)
        except ImportError as exc:
            fail(problems, f"{relative}: cannot import {module}: {exc}")
            continue
        except AttributeError:
            fail(
                problems,
                f"{relative}: {module} exposes no attribute {attribute!r}",
            )
            continue
        except SystemExit:
            # The app refuses to build without configuration. That is correct
            # behaviour; the checker supplies a throwaway value above.
            fail(
                problems,
                f"{relative}: {target} refused to build even with a secret set",
            )
            continue
        if not callable(target_obj):
            fail(problems, f"{relative}: {target} is not an ASGI application")


ALL_DOCKERFILES = (
    "backend/Dockerfile",
    "ml-service/Dockerfile",
    "dashboard/Dockerfile",
)


def check_privileges(problems: list[str]) -> None:
    """Every image in the stack must drop privileges.

    This covers all three Dockerfiles, not only the two with an importable ASGI
    target. The dashboard runs nginx and had no USER line at all, which the
    ASGI-scoped check could never see — a root web server is exactly what a
    privilege check exists to catch.
    """
    for relative in ALL_DOCKERFILES:
        path = os.path.join(ROOT, relative)
        if not os.path.exists(path):
            fail(problems, f"{relative} is missing")
            continue
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        if not re.search(r"^USER\s+\S+", content, re.M):
            fail(problems, f"{relative} does not drop privileges with USER")


def check_dashboard_healthcheck(services: dict[str, Any], problems: list[str]) -> None:
    """The dashboard healthcheck must probe the port nginx actually binds.

    Nothing else validates this service's healthcheck, because it has no ASGI
    app to compare routes against; a stale port here would look like a healthy
    container that serves nothing.
    """
    service = services.get("dashboard", {})
    published = {
        str(entry).split(":")[-1].split("/")[0] for entry in service.get("ports", [])
    }
    test = " ".join(service.get("healthcheck", {}).get("test", []))
    found = re.search(r"localhost:(\d+)", test)
    if not found:
        fail(problems, "dashboard healthcheck has no localhost port")
        return
    if found.group(1) not in published:
        fail(
            problems,
            f"dashboard healthcheck probes port {found.group(1)}, "
            f"but the container publishes {sorted(published)}",
        )


def check_build_contexts(services: dict[str, Any], problems: list[str]) -> None:
    """Every build context must exist on disk."""
    docker_dir = os.path.dirname(COMPOSE)
    for service, (context, _port) in EXPECTED_BUILD.items():
        resolved = os.path.normpath(os.path.join(docker_dir, context))
        declared = services.get(service, {}).get("build", {}).get("context")
        if declared != context:
            fail(
                problems,
                f"{service} build context is {declared!r}, expected {context!r}",
            )
        if not os.path.isdir(resolved):
            fail(problems, f"{service} build context does not exist: {resolved}")


def main() -> int:
    """Run every static check. Returns a process exit code."""
    problems: list[str] = []

    # Importing the applications builds them, and they refuse to build without a
    # secret. This throwaway value is used only for this static check and never
    # serves traffic; it is not a credential (R-50).
    os.environ.setdefault("AEGIS_SECRET_KEY", "K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu")

    if not os.path.exists(COMPOSE):
        print(f"FATAL: {COMPOSE} not found", file=sys.stderr)
        return 2

    compose = load_compose()
    services = check_services(compose, problems)
    check_env_vars(services, problems)
    check_database_driver(services, problems)
    check_secret(services, problems)
    check_ports(services, problems)
    check_healthchecks(services, problems)
    check_dockerfiles(problems)
    check_privileges(problems)
    check_dashboard_healthcheck(services, problems)
    check_build_contexts(services, problems)

    print(
        f"checked {COMPOSE.replace(ROOT + '/', '')}: "
        f"{len(services)} services, {len(EXPECTED_BUILD)} build contexts"
    )
    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  FAIL {problem}", file=sys.stderr)
        return 1

    print("compose static consistency: all checks passed")
    print(
        "note: this does not build images or start the stack — that needs a Docker daemon"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
