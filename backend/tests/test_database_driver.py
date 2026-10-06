"""T-323: the driver every shipped DSN names is the one the backend installs.

The task was raised while running T-321's live migration test: nothing in the
repository installed a PostgreSQL driver, so `alembic upgrade head` could not run
from a plain install -- and the URL the compose stack shipped named ``asyncpg``,
which a *synchronous* Alembic environment cannot use at all, whatever is installed
beside it. Both halves of the criterion are checked here:

* the URL: every PostgreSQL DSN in the repository names the driver the backend
  declares, and no other driver is declared; and
* the install: a subprocess opens an engine on each of those URLs and reports the
  driver it loaded, so the claim is about the installed distribution rather than
  about a string in a file.

The subprocess is not ceremony. ``create_engine`` imports the DBAPI, and importing
``psycopg`` into this process would leave it in ``sys.modules`` for the rest of the
session -- where ``test_golden.py`` asserts that the client libraries for systems
the golden path must not need are never loaded, database drivers included.

The end-to-end half -- `alembic upgrade head` from a plain install against a live
PostgreSQL -- is recorded in D-057 rather than run here: it needs a server, and the
migration suite that does need one skips without ``AEGIS_DATABASE_URL``.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from app.core.config import Settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

#: A PostgreSQL URL, capturing the driver segment: ``postgresql+psycopg://`` is
#: ``psycopg``, and a bare ``postgresql://`` captures nothing, because SQLAlchemy
#: then chooses psycopg2 itself -- which is a driver choice too.
URL_RE = re.compile(r"\bpostgresql(?:\+([a-z0-9_]+))?://")

#: The distribution that provides each SQLAlchemy driver name.
DRIVER_PACKAGES = {"psycopg": "psycopg", "psycopg2": "psycopg2", "asyncpg": "asyncpg"}

#: The driver this repository deploys with, and why (D-057): one driver for
#: Alembic's synchronous engine and for the async engine R-18 will require, since
#: an async-only driver is refused on a synchronous engine no matter what else is
#: installed. Naming it here makes a swap an edit someone has to justify.
EXPECTED_DRIVER = "psycopg"

#: Files that may carry a database URL, relative to a base directory. A new one is
#: caught rather than assumed: the scan is over the files that exist.
URL_FILES = (
    ".env.example",
    "docker/docker-compose.yml",
    "docker/docker-compose.dev.yml",
    "alembic.ini",
)


def _url_files() -> list[Path]:
    """Return the URL-carrying files that exist, from the backend and the root."""
    found: list[Path] = []
    for relative in URL_FILES:
        for base in (BACKEND_ROOT, REPO_ROOT):
            candidate = base / relative
            if candidate.is_file():
                found.append(candidate)
    found.extend(sorted(REPO_ROOT.glob("k8s/**/*.yaml")))
    return found


def _driver_of(url: str) -> str:
    """The driver segment of ``url``, refusing a URL that names none."""
    match = URL_RE.search(url)
    assert match is not None, f"{url} is not a PostgreSQL URL"
    assert match.group(1), (
        f"{url} names no driver, so SQLAlchemy would fall back to psycopg2 -- "
        "a driver nothing here declares"
    )
    return str(match.group(1))


def _shipped_urls() -> list[tuple[str, str]]:
    """Every ``(source, url)`` pair the repository ships."""
    default = Settings.model_fields["database_url"].default
    assert isinstance(default, str)
    pairs = [("Settings.database_url", default)]
    for path in _url_files():
        text = path.read_text(encoding="utf-8")
        for match in URL_RE.finditer(text):
            # A DSN runs to the first whitespace or quote; both shapes here (a bare
            # value in a template, a mapping value in compose) are one token.
            tail = text[match.start() :]
            pairs.append((str(path.relative_to(REPO_ROOT)), re.split(r"""[\s'"]""", tail)[0]))
    return pairs


def _declared_driver_packages() -> set[str]:
    """The PostgreSQL driver distributions ``backend/pyproject.toml`` declares."""
    with (BACKEND_ROOT / "pyproject.toml").open("rb") as handle:
        project: dict[str, Any] = tomllib.load(handle)["project"]
    declared: set[str] = set()
    for requirement in project.get("dependencies", []):
        name = re.split(r"[\[<>=!; ]", str(requirement).strip(), maxsplit=1)[0].lower()
        if name in DRIVER_PACKAGES.values():
            declared.add(name)
    return declared


def _open_engine(url: str) -> subprocess.CompletedProcess[str]:
    """Open an engine on ``url`` in a subprocess and report the driver it loaded."""
    script = (
        "import sys\n"
        "from sqlalchemy import create_engine\n"
        "print(create_engine(sys.argv[1]).dialect.driver)\n"
    )
    return subprocess.run(
        [sys.executable, "-c", script, url],
        cwd=BACKEND_ROOT,
        env={k: v for k, v in os.environ.items() if not k.startswith("AEGIS_")},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


CHECKER = REPO_ROOT / "scripts" / "check_compose.py"
COMPOSE = REPO_ROOT / "docker" / "docker-compose.yml"


def _checker() -> ModuleType:
    """The compose checker, imported without running it, as the docs test does."""
    spec = importlib.util.spec_from_file_location("check_compose", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _problems_for(url: str) -> list[str]:
    """Run the checker's driver rule against a compose file whose DSN is ``url``."""
    checker = _checker()
    services = checker.load_compose()["services"]
    # First URL wins in the checker; keep the mutated one the only PostgreSQL URL.
    environment = services["backend"]["environment"]
    for key, value in list(environment.items()):
        if isinstance(value, str) and URL_RE.search(value):
            del environment[key]
    environment["AEGIS_DATABASE_URL"] = url
    problems: list[str] = []
    checker.check_database_driver(services, problems)
    return problems


def test_the_compose_checker_accepts_what_is_shipped() -> None:
    """The rule is not a check that fails whatever it is shown."""
    problems: list[str] = []
    checker = _checker()
    checker.check_database_driver(checker.load_compose()["services"], problems)
    assert problems == []


def test_the_compose_checker_refuses_a_driver_nothing_declares() -> None:
    """The defect T-323 fixes: asyncpg in the DSN, nothing installing it."""
    problems = _problems_for("postgresql+asyncpg://aegis:aegis@postgres:5432/aegis")
    assert any(
        "asyncpg" in problem and "ModuleNotFoundError" in problem for problem in problems
    ), problems


def test_the_compose_checker_refuses_a_url_with_no_driver() -> None:
    """A bare URL is a driver choice too: SQLAlchemy would reach for psycopg2."""
    problems = _problems_for("postgresql://aegis:aegis@postgres:5432/aegis")
    assert any("names no driver" in problem for problem in problems), problems


def test_the_compose_checker_refuses_a_pyproject_that_declares_no_driver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Declaring the DSN is not enough; the distribution has to be declared too."""
    checker = _checker()
    stripped = tmp_path / "pyproject.toml"
    stripped.write_text(
        (BACKEND_ROOT / "pyproject.toml")
        .read_text(encoding="utf-8")
        .replace('"psycopg[binary]>=3.2",', ""),
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "BACKEND_PYPROJECT", str(stripped))
    problems: list[str] = []
    checker.check_database_driver(checker.load_compose()["services"], problems)
    assert any("declares no PostgreSQL driver" in problem for problem in problems), problems
    assert any("ModuleNotFoundError" in problem for problem in problems), problems


def test_the_rule_is_wired_into_the_run_that_ci_fails_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unwired rule guards nothing: it is main()'s exit code CI reads."""
    checker = _checker()
    mutated = tmp_path / "docker-compose.yml"
    mutated.write_text(
        COMPOSE.read_text(encoding="utf-8").replace(
            "postgresql+psycopg://", "postgresql+asyncpg://"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "COMPOSE", str(mutated))
    assert checker.main() == 1
    assert "asyncpg" in capsys.readouterr().err


def test_the_run_passes_on_the_compose_file_that_is_shipped() -> None:
    """And the same run is green on the real file, so the rule is not always red."""
    assert _checker().main() == 0


def test_every_shipped_url_names_a_driver() -> None:
    """No URL is left driver-less: a bare ``postgresql://`` is a driver choice too."""
    for source, url in _shipped_urls():
        assert _driver_of(url), f"{source} ships {url} without a driver"


def test_every_shipped_url_names_the_declared_driver() -> None:
    """The criterion: the driver the DSN names is the one the backend installs."""
    declared = _declared_driver_packages()
    assert declared == {EXPECTED_DRIVER}, (
        f"backend/pyproject.toml declares {sorted(declared)}; this repository "
        f"deploys with {EXPECTED_DRIVER!r} (D-057)"
    )
    seen = set()
    for source, url in _shipped_urls():
        driver = _driver_of(url)
        seen.add(driver)
        assert DRIVER_PACKAGES.get(driver) in declared, (
            f"{source} ships {url}, whose driver {driver!r} is not declared in "
            "backend/pyproject.toml: `alembic upgrade head` would fail with "
            "ModuleNotFoundError"
        )
    assert seen == {EXPECTED_DRIVER}


def test_the_url_inventory_is_the_one_this_repository_ships() -> None:
    """The scan is pinned, so a DSN that disappears is a failed assertion.

    A template that quietly loses its URL would leave nothing for the checks above
    to examine. Adding a DSN elsewhere means adding it here -- a deliberate edit,
    which is the point.
    """
    assert {source for source, _url in _shipped_urls()} == {
        "Settings.database_url",
        "backend/.env.example",
        "docker/docker-compose.yml",
    }


def test_the_compose_checker_also_checks_the_application_default() -> None:
    """The URL a deployment gets when it sets none is checked, not only compose's."""
    checker = _checker()
    urls = checker.database_urls(checker.load_compose()["services"])
    default = Settings.model_fields["database_url"].default
    assert any(url == default for url in urls), urls


def test_the_backend_declares_exactly_one_driver() -> None:
    """One driver, not a set: a second one can only be opened by mistake."""
    declared = _declared_driver_packages()
    assert len(declared) == 1, f"more than one PostgreSQL driver declared: {sorted(declared)}"


@pytest.mark.parametrize(("source", "url"), _shipped_urls(), ids=lambda value: str(value)[:40])
def test_the_installed_driver_opens_every_shipped_url(source: str, url: str) -> None:
    """A plain install can open the URL it ships, and reports the same driver."""
    del source
    opened = _open_engine(url)
    assert opened.returncode == 0, opened.stderr
    assert opened.stdout.strip() == EXPECTED_DRIVER
