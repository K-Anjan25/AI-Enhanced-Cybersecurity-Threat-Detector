#!/usr/bin/env python3
"""Import-boundary contracts for the dashboard (T-009).

The backend's contracts are enforced by ``import-linter``. The dashboard has no
equivalent installed, and adding a dependency to re-derive something that is
decidable from the source tree is the wrong trade — so this is the frontend
counterpart, written the same way as ``check_docs.py`` and ``check_k8s.py`` and
proven the same way: a deliberate violation must make it fail.

Two contracts, both from ``rules.md``:

* **a feature may not import another feature.** Features are vertical slices
  that are meant to be deletable. The moment ``features/alerts`` reaches into
  ``features/overview`` for a helper, neither can be removed or reordered
  without breaking the other, and the slice boundary becomes decorative.
* **dependencies point down the layering, never up.** ``lib`` knows nothing
  about React, ``theme`` knows nothing about components, and no shared component
  may reach up into a feature — otherwise the component is only reusable inside
  the feature that happens to own the import.

The layering, lowest first::

    lib  ->  api, theme, test  ->  components  ->  features  ->  app shell

``api`` sits beside ``theme``: the typed HTTP client knows nothing about React or
about components (R-23), and features are what use it.

A file may import from its own layer and from anything below it. ``App.tsx`` and
``main.tsx`` sit at the top and may import anything, because composing the tree
is their job.

Only *relative* specifiers are inspected. The dashboard has no ``paths`` alias
in ``tsconfig.json``, so a bare specifier is a package import by construction;
if an alias is ever added, this script must learn to resolve it, and saying so
here is cheaper than discovering a silently unchecked import path later.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_compose import ROOT, fail  # noqa: E402

SRC_DIR = os.path.join(ROOT, "dashboard", "src")

#: Extensions treated as dashboard source.
EXTENSIONS = (".ts", ".tsx", ".mts", ".cts")

#: Rank per top-level directory under ``src``. Higher may import lower.
LAYER_RANK: dict[str, int] = {
    "lib": 0,
    "theme": 1,
    "test": 1,
    # The typed API client (R-23): below components, because a shared presentational
    # component has no business making requests.
    "api": 1,
    "components": 2,
    "features": 3,
}

#: Rank of the files sitting directly in ``src`` — the app shell that wires the
#: tree together. Deliberately above every layer.
SHELL_RANK = 4

#: ``import ... from '...'``, ``import '...'``, ``export ... from '...'`` and
#: ``import type { ... } from '...'``. Only the specifier is captured.
_STATIC_IMPORT = re.compile(
    r"""(?:^|[\s;}])(?:import|export)\b[^'"()]*?\bfrom\s*['"]([^'"]+)['"]""",
    re.MULTILINE,
)

#: Side-effect imports, which have no ``from`` clause.
_BARE_IMPORT = re.compile(r"""\bimport\s*['"]([^'"]+)['"]""")

#: Dynamic ``import('...')``.
_DYNAMIC_IMPORT = re.compile(r"""\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)""")


def source_files() -> list[str]:
    """Every dashboard source file, sorted so failures are reported in order."""
    found: list[str] = []
    for directory, _directories, filenames in os.walk(SRC_DIR):
        for filename in filenames:
            if filename.endswith(EXTENSIONS):
                found.append(os.path.join(directory, filename))
    return sorted(found)


def specifiers(path: str) -> list[str]:
    """Every import specifier in a file, in source order."""
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    seen = [
        *_STATIC_IMPORT.findall(source),
        *_BARE_IMPORT.findall(source),
        *_DYNAMIC_IMPORT.findall(source),
    ]
    # Relative imports only; see the module docstring on why that is sound here.
    return [spec for spec in seen if spec.startswith(".")]


def resolve(path: str, specifier: str) -> str:
    """Resolve a relative specifier to an extension-less path under ``src``."""
    return os.path.normpath(os.path.join(os.path.dirname(path), specifier))


def resolve_source_file(path: str, specifier: str) -> str | None:
    """Return the source file a specifier points at, or None if it is not one.

    Specifiers omit extensions, so resolution has to try them — the same way the
    bundler does, including the ``index`` convention for directory imports.

    Returning None covers two different cases, which the caller tells apart: a
    stylesheet or other asset, and a specifier that resolves to nothing at all.
    The second is a broken import, and reporting it here is cheaper than letting
    a typo survive because the boundary check walked straight past it.
    """
    target = resolve(path, specifier)
    if target.endswith(EXTENSIONS) and os.path.isfile(target):
        return target
    for extension in EXTENSIONS:
        candidate = target + extension
        if os.path.isfile(candidate):
            return candidate
        index = os.path.join(target, "index" + extension)
        if os.path.isfile(index):
            return index
    return None


def parts(path: str) -> tuple[str | None, str | None]:
    """Return ``(layer, feature)`` for a file, or ``(None, None)`` for the shell.

    ``feature`` is set only for files inside ``src/features/<name>/``.
    """
    relative = os.path.relpath(path, SRC_DIR).replace(os.sep, "/")
    segments = relative.split("/")
    if len(segments) == 1:
        return None, None
    layer = segments[0]
    feature = segments[1] if layer == "features" and len(segments) > 2 else None
    return layer, feature


def rank_of(layer: str | None) -> int:
    """The layer's rank; the shell and anything unlisted compose everything."""
    return SHELL_RANK if layer is None else LAYER_RANK.get(layer, SHELL_RANK)


def label(path: str) -> str:
    """A repo-relative path, for readable failure messages."""
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def check_boundaries(problems: list[str]) -> tuple[int, int]:
    """Walk every source file and report contract violations.

    Returns the number of files inspected and the number of relative imports
    checked, so the summary can show that the walk covered the tree rather than
    a convenient subset of it.
    """
    files = source_files()
    edges = 0
    for path in files:
        importer_layer, importer_feature = parts(path)
        importer_rank = rank_of(importer_layer)
        for specifier in specifiers(path):
            target = resolve(path, specifier)
            edges += 1
            # An import that escapes ``src`` (into a sibling package, say) is
            # outside these contracts; leaving the tree is reported, not ignored
            # silently, because it is almost always a mistake.
            if not target.startswith(SRC_DIR + os.sep):
                fail(
                    problems,
                    f"{label(path)} imports '{specifier}', which leaves src/ — "
                    "outside every boundary contract",
                )
                continue
            source = resolve_source_file(path, specifier)
            if source is None:
                # A stylesheet or other asset is a side-effect import, not a
                # module boundary. Anything that is not a file at all is a
                # broken import.
                if not os.path.exists(target):
                    fail(
                        problems,
                        f"{label(path)} imports '{specifier}', which resolves to no "
                        "file under src/",
                    )
                continue
            target_layer, target_feature = parts(target)
            target_rank = rank_of(target_layer)

            if (
                importer_feature
                and target_feature
                and importer_feature != target_feature
            ):
                fail(
                    problems,
                    f"{label(path)} (feature '{importer_feature}') imports "
                    f"'{specifier}' from feature '{target_feature}' — features must "
                    "not import each other; move the shared code to components/ or lib/",
                )
                continue

            if target_rank > importer_rank:
                fail(
                    problems,
                    f"{label(path)} ({importer_layer or 'app shell'}) imports "
                    f"'{specifier}' from {target_layer}, a higher layer — dependencies "
                    "point down: lib -> theme/test -> components -> features -> shell",
                )
    return len(files), edges


def main() -> int:
    """Check the dashboard's import boundaries. Returns a process exit code."""
    if not os.path.isdir(SRC_DIR):
        print(f"no dashboard source at {label(SRC_DIR)}", file=sys.stderr)
        return 1

    problems: list[str] = []
    files, edges = check_boundaries(problems)

    print(f"checked {files} source files, {edges} relative import(s)")
    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  FAIL {problem}", file=sys.stderr)
        return 1

    print("frontend import boundaries: all contracts hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
