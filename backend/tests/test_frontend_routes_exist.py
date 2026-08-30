"""Every API path the dashboard calls must exist on the backend.

Four ModulePage sources once pointed at endpoints that had never existed
(`/deception/decoys`, `/forensics/evidence`, `/tip/indicators`,
`/attack-navigator/heatmap`). Nothing caught it: the frontend tests mock the
API client, and a 404 renders as an empty section that looks exactly like
"no data yet". The bug was only visible by running the stack by hand.

This test closes that gap by reading the paths the dashboard actually declares
and asserting each one is a real route, so a typo or a renamed endpoint fails
in CI instead of showing the operator a calm, empty page.
"""

import re
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[2] / "dashboard" / "src"
MODULE_PAGE = DASHBOARD / "features" / "modules" / "pages" / "ModulePage.tsx"

# Paths built at call time from a variable (e.g. `/cases/${id}`) cannot be
# checked statically; only literal `path: "/..."` entries are verified.
PATH_LITERAL = re.compile(r'path:\s*"(/[^"]*)"')


def _declared_paths() -> list[str]:
    if not MODULE_PAGE.exists():  # pragma: no cover - guards a moved file
        pytest.skip(f"{MODULE_PAGE} not found")
    return sorted(set(PATH_LITERAL.findall(MODULE_PAGE.read_text())))


def _known_routes(app) -> set[str]:
    """Read the OpenAPI schema rather than app.routes.

    This FastAPI version wraps included routers in an internal `_IncludedRouter`
    object that does not expose nested routes, so walking `app.routes` finds
    only the handful of top-level paths. The generated schema is the reliable,
    version-independent source.
    """
    return set(app.openapi()["paths"])


def test_module_page_declares_paths():
    """Guard the guard: if the regex stops matching, this test is worthless."""
    paths = _declared_paths()
    assert len(paths) > 10, f"expected many declared paths, found {paths}"


@pytest.mark.parametrize("path", _declared_paths())
def test_declared_path_is_a_real_route(path):
    """A path the UI fetches must resolve, so 404 never masquerades as empty."""
    from app.main import app

    full = f"/api/v1{path}"
    routes = _known_routes(app)

    # FastAPI registers "/sbom/" and "/sbom" distinctly; accept either form.
    candidates = {full, full.rstrip("/"), full + "/"}
    assert candidates & routes, (
        f"ModulePage fetches {full}, which is not a registered route. "
        f"It would render as an empty section rather than an error."
    )


def test_no_declared_path_targets_a_removed_capability():
    """The cut Labs modules must not creep back into the UI."""
    removed = [
        "data_lake", "data-lake", "federated", "compliance-autopilot",
        "ai-redteam", "agent-collab", "finetune", "pdf-export", "marketplace",
    ]
    declared = " ".join(_declared_paths())
    for name in removed:
        assert name not in declared, f"{name} was removed from the backend"
