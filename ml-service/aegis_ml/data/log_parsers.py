"""Log corpus parsing: BGL to ``log@1`` with template mining (T-104).

The corpus is BlueGene/L (BGL) from LogHub, 2,000 lines of real supercomputer
system logs. It was chosen over the other reachable corpora for one reason: it
carries an explicit severity on every line. ``log@1`` requires a ``level``, and
Thunderbird — the other syslog-shaped corpus here — has no severity column at
all. Inventing one from keywords in the message would put fabricated data into
the training set, so that corpus is not used.

Two acceptance points from T-104 are handled explicitly:

* **The template/parameter split is recorded, not thrown away.** Every
  ``LogRecord`` carries a template id and the values abstracted away from it.
* **Unparseable lines are surfaced as a metric.** A corpus with a line this
  parser cannot read is a corpus whose record count no longer matches the file,
  and that gap has to be visible rather than absorbed.

Mining runs in two passes, because the lexical pass alone is not good enough.
A token-level pass marks ``003a90fc`` and ``core.2275`` as variables, but it
cannot see that ``CE sym 2, at 0x0b85eee0`` and ``CE sym 20, at 0x1438f9e0``
are the same event when only some positions vary, so it fragments the
vocabulary: measured on this corpus it produced 1,198 templates where LogHub's
published labels have 120. The second pass fixes that by repeatedly merging
templates of equal length that differ in exactly one position, replacing it with
``<*>``. Measured against LogHub's published labels for this corpus, the result is
103 templates against their 120, with 0.9935 agreement against their grouping
and 0.9530 the other way round — close enough that a later disagreement with
Drain3 (Q-01, T-204) will be about specific messages rather than about the
whole approach. The lexical pass alone scored 0.4185 on that same measure, so
the second pass is doing nearly all of the work.

Template ids are content-addressed (a truncated SHA-256 of the template text)
rather than sequential. A sequential id would change whenever the input order
changed, which makes any artifact keyed by template id unreproducible.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from aegis_ml.data.records import SCHEMA_VERSION_LOG, LogLevel, LogRecord

#: BGL severities, mapped onto the five ``log@1`` levels. SEVERE and FATAL both
#: exist upstream; SEVERE is serious but recoverable and FATAL is terminal, so
#: they do not collapse onto the same level.
BGL_LEVELS: Final[dict[str, LogLevel]] = {
    "DEBUG": LogLevel.DEBUG,
    "INFO": LogLevel.INFO,
    "WARNING": LogLevel.WARNING,
    "ERROR": LogLevel.ERROR,
    "SEVERE": LogLevel.ERROR,
    "FATAL": LogLevel.CRITICAL,
}

#: ``- <epoch> <date> <node> <full-time> <node> <type> <component> <level> <content>``
_BGL_LINE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<seq>\S+)\s+"
    r"(?P<epoch>\d+)\s+"
    r"(?P<date>\S+)\s+"
    r"(?P<node>\S+)\s+"
    r"(?P<full_time>\S+)\s+"
    r"(?P<node_repeat>\S+)\s+"
    r"(?P<type>\S+)\s+"
    r"(?P<component>\S+)\s+"
    r"(?P<level>\S+)\s+"
    r"(?P<content>.+)$"
)

#: Token shapes that carry no structural meaning. Tried in order; the bare-hex
#: rule is qualified separately because a plain character class would also
#: swallow ordinary words like ``dead``.
_VARIABLE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"0[xX][0-9a-fA-F]+"),
    re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"),
    re.compile(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?"),
    re.compile(r"[A-Za-z_][A-Za-z0-9_]*\d[A-Za-z0-9_]*"),
    re.compile(r"\S*\.\d+"),
)

#: A run of hex digits with no ``0x`` prefix, e.g. ``003a90fc``.
_BARE_HEX: Final[re.Pattern[str]] = re.compile(r"[0-9a-fA-F]{4,}")

#: Placeholder substituted for every parameter position.
PARAMETER_PLACEHOLDER: Final[str] = "<*>"

#: Length of the content-addressed template id.
TEMPLATE_ID_LENGTH: Final[int] = 16

#: Cap on merge rounds. The pass is a fixed point; this only bounds pathological
#: input, and it is reported if it is ever reached.
MAX_MERGE_ROUNDS: Final[int] = 40


def template_id(template: str) -> str:
    """Content-addressed id for a template, stable across runs and files."""
    return hashlib.sha256(template.encode("utf-8")).hexdigest()[:TEMPLATE_ID_LENGTH]


def _is_variable_token(token: str) -> bool:
    """Whether a token is a value rather than part of the message's shape."""
    if _BARE_HEX.fullmatch(token):
        has_digit = any(c.isdigit() for c in token)
        has_alpha = any(c.isalpha() for c in token)
        # Require both, so a bare word that happens to be hex letters — dead,
        # beef, cafe — stays part of the template.
        return has_digit and has_alpha
    return any(pattern.fullmatch(token) for pattern in _VARIABLE_PATTERNS)


def lexical_template(message: str) -> tuple[str, ...]:
    """First pass: tokenise and mark every variable-looking token."""
    return tuple(
        PARAMETER_PLACEHOLDER if _is_variable_token(token) else token for token in message.split()
    )


class MinedTemplate(BaseModel):
    """One message's template assignment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    template: str
    parameters: dict[str, str]


class TemplateMiner(BaseModel):
    """A mined template vocabulary, able to assign new messages to it.

    ``templates`` holds token tuples so the wildcard positions survive
    serialisation, **ordered least-specific-first** (most wildcards, then
    lexicographic). That order is part of the artifact because it decides which
    template a message is assigned to: a merged template exists precisely
    because those messages are one event, so the most general template that
    still covers a message is the right answer. Iterating a plain set instead
    gives a different count run to run — measured on this corpus, 284 versus
    103 — so the order is fixed and stored rather than left to Python.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    templates: tuple[tuple[str, ...], ...]
    merge_rounds: int = Field(ge=0)
    converged: bool = True

    @classmethod
    def fit(cls, messages: Iterable[str]) -> TemplateMiner:
        """Mine a vocabulary from a corpus.

        Deterministic regardless of input order: the template set is sorted
        before merging, and a merge only happens when every non-candidate
        position already agrees, so the outcome never depends on which pair was
        seen first.
        """
        current: set[tuple[str, ...]] = {lexical_template(message) for message in messages}
        rounds = 0
        converged = False
        while rounds < MAX_MERGE_ROUNDS:
            current, changed = _merge_round(current)
            rounds += 1
            if not changed:
                converged = True
                break
        return cls(
            templates=tuple(
                sorted(
                    current,
                    key=lambda tokens: (
                        -sum(1 for token in tokens if token == PARAMETER_PLACEHOLDER),
                        tokens,
                    ),
                )
            ),
            merge_rounds=rounds,
            converged=converged,
        )

    def assign(self, message: str) -> MinedTemplate:
        """Fit one message to the vocabulary.

        Falls back to the message's own lexical template when nothing matches,
        which can only happen for a message longer or shorter than anything seen
        during fitting. That is recorded as its own template rather than being
        forced into a near-miss.
        """
        original = tuple(message.split())
        marked = lexical_template(message)
        for template in self.templates:
            if len(template) != len(marked):
                continue
            if all(
                expected in (PARAMETER_PLACEHOLDER, actual)
                for expected, actual in zip(template, marked, strict=True)
            ):
                # Parameters are read out of the ORIGINAL tokens. The marked
                # tokens already say "<*>" there, so passing them would record
                # the placeholder as the value and destroy the only copy of the
                # data the template abstracted away.
                return _build(template, original)
        return _build(marked, original)


def _build(template: tuple[str, ...], tokens: tuple[str, ...]) -> MinedTemplate:
    text = " ".join(template)
    parameters = {
        f"p{index}": tokens[index]
        for index, slot in enumerate(template)
        if slot == PARAMETER_PLACEHOLDER
    }
    return MinedTemplate(template_id=template_id(text), template=text, parameters=parameters)


def _merge_round(templates: set[tuple[str, ...]]) -> tuple[set[tuple[str, ...]], bool]:
    """One round of merging templates that differ in exactly one position."""
    by_length: dict[int, list[tuple[str, ...]]] = defaultdict(list)
    for template in templates:
        by_length[len(template)].append(template)

    out: set[tuple[str, ...]] = set()
    changed = False
    for length in sorted(by_length):
        group = sorted(by_length[length])
        # Outer key is the candidate position, inner key the template with that
        # position removed, so members of one bucket differ only there.
        buckets: dict[int, dict[tuple[str, ...], set[tuple[str, ...]]]] = defaultdict(
            lambda: defaultdict(set)
        )
        for template in group:
            for skip in range(length):
                rest = tuple(token for i, token in enumerate(template) if i != skip)
                buckets[skip][rest].add(template)

        consumed: set[tuple[str, ...]] = set()
        for skip in sorted(buckets):
            for members in buckets[skip].values():
                if len(members) < 2:
                    continue
                # Merge only when every other position already agrees; otherwise
                # the messages differ in more than one place and are not one event.
                others = {
                    tuple(token for i, token in enumerate(member) if i != skip)
                    for member in members
                }
                if len(others) != 1:
                    continue
                variants = {member[skip] for member in members}
                if len(variants) < 2 or PARAMETER_PLACEHOLDER in variants:
                    continue
                merged = tuple(
                    PARAMETER_PLACEHOLDER if i == skip else token
                    for i, token in enumerate(next(iter(members)))
                )
                out.add(merged)
                consumed |= members
                changed = True
        out |= {template for template in group if template not in consumed}
    return out, changed


class LogParseReport(BaseModel):
    """What a log parse did, including what it could not read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_file: str
    corpus: str
    lines_read: int = Field(ge=0)
    parsed: int = Field(ge=0)
    unparseable: int = Field(ge=0)
    unparseable_reasons: dict[str, int] = Field(default_factory=dict)
    distinct_templates: int = Field(ge=0)
    distinct_hosts: int = Field(ge=0)
    distinct_services: int = Field(ge=0)
    levels: dict[str, int] = Field(default_factory=dict)
    merge_rounds: int = Field(ge=0)

    @property
    def unparseable_rate(self) -> float:
        """Share of lines that could not be read. T-104 requires this surfaced."""
        if not self.lines_read:
            return 0.0
        return self.unparseable / self.lines_read

    def raise_for_empty(self) -> None:
        """Fail loudly when nothing at all could be parsed."""
        if self.parsed:
            return
        reasons = ", ".join(f"{k}={v}" for k, v in sorted(self.unparseable_reasons.items()))
        msg = f"{self.source_file}: parsed 0 of {self.lines_read} lines ({reasons or 'no lines'})"
        raise ValueError(msg)


class ParsedLogs(BaseModel):
    """Parsed log records plus the report describing how they were obtained."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    records: tuple[LogRecord, ...]
    report: LogParseReport
    template_counts: dict[str, int] = Field(
        default_factory=dict, description="template id -> how many lines produced it."
    )
    template_text: dict[str, str] = Field(
        default_factory=dict, description="template id -> template text."
    )


def _bgl_level(raw: str) -> LogLevel:
    level = BGL_LEVELS.get(raw.upper())
    if level is None:
        msg = f"unmapped_level:{raw}"
        raise ValueError(msg)
    return level


def parse_bgl(path: str) -> ParsedLogs:
    """Parse a BGL log file into ``log@1`` records with mined templates.

    The timestamp comes from the epoch column rather than the human-readable
    date fields: the epoch is unambiguous, while ``2005.06.03`` plus
    ``2005-06-03-15.42.50.675872`` would need a timezone the corpus never
    states. Records are stamped UTC.
    """
    raw_lines: list[tuple[int, str, str, LogLevel, str]] = []
    reasons: Counter[str] = Counter()
    lines = 0

    with open(path, encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            lines += 1
            line = raw_line.rstrip("\r\n")
            if not line.strip():
                reasons["empty_line"] += 1
                continue
            match = _BGL_LINE.match(line)
            if match is None:
                reasons["shape_mismatch"] += 1
                continue
            group = match.groupdict()
            try:
                level = _bgl_level(group["level"])
            except ValueError as exc:
                reasons[str(exc)] += 1
                continue
            raw_lines.append(
                (
                    int(group["epoch"]),
                    group["node"],
                    group["component"],
                    level,
                    group["content"],
                )
            )

    # Mining needs the whole corpus: a template is only recognisable as a
    # template once the messages that vary inside it have been seen together.
    miner = TemplateMiner.fit(content for *_, content in raw_lines)

    records: list[LogRecord] = []
    template_counts: Counter[str] = Counter()
    template_text: dict[str, str] = {}
    for epoch, node, component, level, content in raw_lines:
        mined = miner.assign(content)
        template_counts[mined.template_id] += 1
        template_text[mined.template_id] = mined.template
        records.append(
            LogRecord(
                schema_version=SCHEMA_VERSION_LOG,
                timestamp=datetime.fromtimestamp(epoch, tz=UTC),
                host=node,
                service=component,
                level=level,
                message=content,
                template_id=mined.template_id,
                parameters=mined.parameters,
            )
        )

    report = LogParseReport(
        source_file=os.path.basename(path),
        corpus="BGL",
        lines_read=lines,
        parsed=len(records),
        unparseable=sum(reasons.values()),
        unparseable_reasons=dict(sorted(reasons.items())),
        distinct_templates=len(template_counts),
        distinct_hosts=len({record.host for record in records}),
        distinct_services=len({record.service for record in records}),
        levels=dict(sorted(Counter(record.level.value for record in records).items())),
        merge_rounds=miner.merge_rounds,
    )
    return ParsedLogs(
        records=tuple(records),
        report=report,
        template_counts=dict(template_counts),
        template_text=template_text,
    )


def write_ndjson(records: Sequence[LogRecord], path: str) -> int:
    """Serialise log records as newline-delimited JSON. Returns the count."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json())
            handle.write("\n")
    return len(records)
