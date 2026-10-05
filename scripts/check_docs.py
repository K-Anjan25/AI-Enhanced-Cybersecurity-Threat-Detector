#!/usr/bin/env python3
"""Documentation integrity checks for the six AEGIS planning documents.

The planning documents are the specification: they cross-reference each other by
anchor and by requirement/task/rule id, and they contain hand-written tables. All
three rot silently, so CI verifies them (rule R-94).

Checks performed:
  1. Every relative markdown link resolves to a file that exists.
  2. Every fragment (#anchor) resolves to a real heading in the target file,
     using GitHub's slug rules.
  3. Every referenced id (T-, R-, FR-, NFR-, D-, Q-) is defined somewhere.
  4. Code fences are balanced, so a stray ``` cannot swallow a section.
  5. Markdown tables are internally consistent (uniform column counts).
  6. Every document links to the other five, so the set stays navigable.

Exits non-zero on the first category of failure, printing every problem found.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter

DOCS = ["prd.md", "architecture.md", "rules.md", "design.md", "task.md", "memory.md"]

# id prefix -> the document that defines it
ID_DEFINITIONS = {
    r"\bT-\d{3}\b": "task.md",
    r"\bR-\d{2}\b": "rules.md",
    r"\bFR-\d{2}\b": "prd.md",
    r"\bNFR-\d{2}\b": "prd.md",
    r"\bD-\d{3}\b": "memory.md",
    r"\bQ-\d{2}\b": "memory.md",
}

ID_LABELS = {
    r"\bT-\d{3}\b": "tasks",
    r"\bR-\d{2}\b": "rules",
    r"\bFR-\d{2}\b": "FR",
    r"\bNFR-\d{2}\b": "NFR",
    r"\bD-\d{3}\b": "decisions",
    r"\bQ-\d{2}\b": "questions",
}

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
TABLE_ROW_RE = re.compile(r"^\s*\|")


def github_slug(text: str) -> str:
    """Reproduce GitHub's heading-to-anchor slug algorithm."""
    lowered = text.strip().lower().replace("`", "")
    kept = [c for c in lowered if c.isalnum() or c in (" ", "-", "_")]
    return "".join(kept).replace(" ", "-")


def read(path: str) -> str:
    """Read a document as UTF-8 text."""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def lines_outside_fences(path: str) -> list[tuple[int, str]]:
    """Return (lineno, line) for lines that are not inside a fenced code block."""
    result: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(read(path).split("\n"), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            result.append((lineno, line))
    return result


def collect_headings(path: str) -> set[str]:
    """Collect every heading slug in a document."""
    return {
        github_slug(m.group(2))
        for _, line in lines_outside_fences(path)
        if (m := HEADING_RE.match(line))
    }


def check_links(problems: list[str], headings: dict[str, set[str]]) -> None:
    """Verify every relative link target and fragment."""
    for doc in DOCS:
        for label, target in LINK_RE.findall(read(doc)):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, anchor = target.partition("#")
            if not path and not anchor:
                continue
            target_file = path if path else doc
            if not os.path.exists(target_file):
                problems.append(f"{doc}: link to missing file '{target}'")
                continue
            if (
                anchor
                and target_file in headings
                and anchor not in headings[target_file]
            ):
                problems.append(f"{doc}: broken anchor '{target}' (text: {label})")


def check_fences(problems: list[str]) -> None:
    """A stray fence silently swallows the rest of a document."""
    for doc in DOCS:
        markers = sum(
            1 for line in read(doc).split("\n") if line.lstrip().startswith("```")
        )
        if markers % 2:
            problems.append(f"{doc}: unbalanced code fences ({markers} markers)")


def check_ids(problems: list[str], texts: dict[str, str]) -> dict[str, set[str]]:
    """Verify every referenced id is defined in its owning document."""
    defined: dict[str, set[str]] = {}
    for pattern, source in ID_DEFINITIONS.items():
        defined[pattern] = set(re.findall(pattern, texts[source]))
    for doc, text in texts.items():
        for pattern, pool in defined.items():
            for ref in set(re.findall(pattern, text)):
                if ref not in pool:
                    problems.append(f"{doc}: references undefined id {ref}")
    return defined


def check_one_table(
    doc: str, block: list[tuple[int, str]], problems: list[str]
) -> None:
    """Verify one table block has a uniform column count."""
    if len(block) < 2:
        return
    counts = [row.count("|") for _, row in block]
    if len(set(counts)) == 1:
        return
    expected = Counter(counts).most_common(1)[0][0]
    for lineno, row in block:
        if row.count("|") != expected:
            problems.append(
                f"{doc}:{lineno} table row has {row.count('|')} pipes, "
                f"expected {expected}: {row[:70]}"
            )


def check_tables(problems: list[str]) -> int:
    """Every row of a table must have the same number of pipe separators."""
    total = 0
    for doc in DOCS:
        block: list[tuple[int, str]] = []
        for lineno, line in lines_outside_fences(doc):
            if TABLE_ROW_RE.match(line):
                block.append((lineno, line.strip()))
                continue
            if block:
                total += 1
                check_one_table(doc, block, problems)
                block = []
        if block:
            total += 1
            check_one_table(doc, block, problems)
    return total


def check_cross_links(problems: list[str], texts: dict[str, str]) -> None:
    """Each document should link to the other five."""
    for doc in DOCS:
        missing = [other for other in DOCS if other != doc and other not in texts[doc]]
        if missing:
            problems.append(f"{doc}: does not link to {', '.join(missing)}")


def main() -> int:
    """Run every check and report. Returns a process exit code."""
    for doc in DOCS:
        if not os.path.exists(doc):
            print(f"FATAL: {doc} is missing; expected all of {DOCS}", file=sys.stderr)
            return 2

    texts = {doc: read(doc) for doc in DOCS}
    headings = {doc: collect_headings(doc) for doc in DOCS}
    problems: list[str] = []

    check_links(problems, headings)
    check_fences(problems)
    defined = check_ids(problems, texts)
    tables = check_tables(problems)
    check_cross_links(problems, texts)

    counts = {ID_LABELS[pattern]: len(pool) for pattern, pool in defined.items()}
    print(
        f"checked {len(DOCS)} documents, {tables} tables, "
        f"{sum(counts.values())} ids ({', '.join(f'{k}={v}' for k, v in counts.items())})"
    )

    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  FAIL {problem}", file=sys.stderr)
        return 1

    print("documentation integrity: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
