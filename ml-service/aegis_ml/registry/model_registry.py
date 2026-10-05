"""Immutable, content-addressed model registry (T-212, R-68).

R-68 states three prohibitions and each one is enforced here rather than assumed.

**No ``latest``.** Not merely absent — actively refused. An id that resolves to
"whatever is newest" means a score cannot be attributed to a model, and an audit
that asks which version flagged a flow gets no answer. :func:`get` raises
:class:`ForbiddenModelId` for it with an explanation, rather than the generic
"not loaded" a missing id would produce, because the two failures have different
remedies: one is a typo, the other is a caller using a pattern this system
forbids.

**No overwriting an artifact.** A model id, once registered, is bound to the
content address it was registered with. Re-registering the same id with different
bytes is refused; re-registering the same id with the same bytes is a no-op. That
distinction matters — a redeploy of an unchanged artifact is normal, while a
silent content change under a stable name is how a supply-chain substitution
would hide.

**No in-place weight edits.** Status is the only mutable thing about a registered
model, and it moves only along the transitions in :data:`ALLOWED_TRANSITIONS`.
``retired`` is terminal: a retired version can never be promoted again, because
allowing it would mean the set of versions that have ever served traffic is not
append-only, and the history stops being a history.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

ModelKind = Literal["flow", "log"]
ModelStatus = Literal["staging", "active", "retired"]

#: Ids this registry refuses to resolve, per R-68. Case-insensitive.
FORBIDDEN_MODEL_IDS: frozenset[str] = frozenset({"latest", "stable", "current", "newest"})

#: Legal status transitions. ``retired`` is terminal on purpose: see the module
#: docstring. There is no path back to ``staging`` either, so a version cannot be
#: quietly re-qualified after it has served traffic.
ALLOWED_TRANSITIONS: dict[ModelStatus, frozenset[ModelStatus]] = {
    "staging": frozenset({"active", "retired"}),
    "active": frozenset({"retired"}),
    "retired": frozenset(),
}

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

#: Bytes read at a time when hashing an artifact.
_HASH_CHUNK = 1 << 20


def content_address_bytes(data: bytes) -> str:
    """The content address of raw artifact bytes."""
    return hashlib.sha256(data).hexdigest()


def content_address(path: str | Path) -> str:
    """The content address of an artifact on disk.

    Read in chunks: model artifacts are megabytes and loading one whole to hash
    it would spike memory in a container sized for inference.

    Raises:
        FileNotFoundError: if the artifact is not there.
    """
    target = Path(path)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


class RegistryError(RuntimeError):
    """Base class for every refusal this registry can make."""


class ModelNotLoaded(RegistryError):
    """Raised when a requested model is not resident in this process.

    The message names the model id so the caller can report precisely what is
    missing rather than a generic failure (rule R-06).
    """


class ForbiddenModelId(RegistryError):
    """Raised for an id R-68 forbids, such as ``latest``.

    Distinct from :class:`ModelNotLoaded` because the remedy differs: a missing id
    is a typo to correct, while a forbidden one is a pattern the caller must stop
    using.
    """


class ImmutableArtifact(RegistryError):
    """Raised when a registered id is re-registered with different content."""


class InvalidTransition(RegistryError):
    """Raised for a status change :data:`ALLOWED_TRANSITIONS` does not allow."""


def _check_forbidden(model_id: str) -> None:
    """Refuse a floating id before anything else looks at it."""
    if model_id.strip().lower() in FORBIDDEN_MODEL_IDS:
        raise ForbiddenModelId(
            f"{model_id!r} is not a resolvable model id. R-68 forbids floating "
            f"references: ask for a specific version, or for the active model of a "
            f"kind via active(). Forbidden: {sorted(FORBIDDEN_MODEL_IDS)}"
        )


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Metadata for one registered model artifact.

    Attributes:
        model_id: immutable identifier. Never ``latest``.
        kind: which model this is. FR-30 requires at least two kinds.
        status: staging, active or retired.
        sha256: content address of the artifact bytes (R-68).
        loaded_at: when this process took the model into memory.
    """

    model_id: str
    kind: ModelKind
    status: ModelStatus
    sha256: str
    loaded_at: datetime

    def __post_init__(self) -> None:
        """Reject an id or content address that could not identify an artifact."""
        _check_forbidden(self.model_id)
        if not _HEX64.match(self.sha256):
            raise ValueError(
                f"model {self.model_id!r} has content address {self.sha256!r}, which is "
                "not a lowercase hex sha256. R-68 requires artifacts to be "
                "content-addressed, so an absent or malformed address is refused "
                "rather than defaulted."
            )

    @property
    def is_serving(self) -> bool:
        """Whether this version is allowed to produce published scores."""
        return self.status == "active"


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """What one :meth:`ModelRegistry.promote` call changed.

    Attributes:
        promoted: the model that became active.
        retired: the incumbent that had to step down, or ``None``.
    """

    promoted: ModelInfo
    retired: ModelInfo | None


class ModelRegistry:
    """Tracks which model versions this process holds in memory."""

    def __init__(self) -> None:
        """Start with no models resident; nothing is loaded implicitly."""
        self._models: dict[str, ModelInfo] = {}

    def register(self, info: ModelInfo) -> None:
        """Record a loaded model.

        Re-registering an id with the *same* content address is a no-op, so an
        unchanged redeploy does not fail. Re-registering it with *different* bytes
        is refused: that is R-68's prohibition on overwriting an artifact.

        Raises:
            ImmutableArtifact: if the id is registered against other content.
            ValueError: if another model of the same kind is already ``active``.
                Two active versions of one kind would make scores ambiguous.
        """
        _check_forbidden(info.model_id)
        existing = self._models.get(info.model_id)
        if existing is not None:
            if existing.sha256 != info.sha256:
                raise ImmutableArtifact(
                    f"model {info.model_id!r} is already registered against content "
                    f"{existing.sha256[:12]}… and cannot be re-registered against "
                    f"{info.sha256[:12]}…. R-68 forbids overwriting an artifact: "
                    "register the new bytes under a new model id."
                )
            return
        if info.status == "active":
            incumbent = self.active(info.kind)
            if incumbent is not None:
                raise ValueError(
                    f"model {incumbent.model_id!r} is already active for kind "
                    f"{info.kind!r}; retire it before promoting another"
                )
        self._models[info.model_id] = info

    def _transition(self, model_id: str, to: ModelStatus) -> ModelInfo:
        """Move a registered model to ``to``, enforcing the transition table."""
        info = self.get(model_id)
        if to == info.status:
            return info
        if to not in ALLOWED_TRANSITIONS[info.status]:
            allowed = sorted(ALLOWED_TRANSITIONS[info.status])
            raise InvalidTransition(
                f"model {model_id!r} is {info.status!r} and cannot move to {to!r}. "
                f"Allowed from {info.status!r}: {allowed or 'nothing — the status is terminal'}."
                + (
                    " A retired version stays retired: register the retrained "
                    "artifact under a new model id instead."
                    if info.status == "retired"
                    else ""
                )
            )
        moved = replace(info, status=to)
        self._models[model_id] = moved
        return moved

    def promote(self, model_id: str) -> PromotionResult:
        """Make ``model_id`` the active model of its kind.

        The incumbent of that kind is retired in the same call. Promotion and
        retirement as two calls would leave a window where either two versions are
        active or none is, and T-315 requires rollback to be one call.

        Promoting an already-active model is idempotent and retires nothing.

        Raises:
            ModelNotLoaded: if the id is unknown.
            InvalidTransition: if the model is retired, which is terminal.
        """
        _check_forbidden(model_id)
        info = self.get(model_id)
        if info.status == "active":
            return PromotionResult(promoted=info, retired=None)
        if info.status == "retired":
            raise InvalidTransition(
                f"model {model_id!r} is retired and cannot be promoted. Retirement "
                "is terminal under R-68: the set of versions that have served "
                "traffic must stay append-only, so a retired model is never reused. "
                "Register the retrained artifact under a new model id."
            )
        incumbent = self.active(info.kind)
        retired = self._transition(incumbent.model_id, "retired") if incumbent else None
        promoted = self._transition(model_id, "active")
        return PromotionResult(promoted=promoted, retired=retired)

    def retire(self, model_id: str) -> ModelInfo:
        """Mark a model retired so another version of its kind can be promoted.

        Raises:
            ModelNotLoaded: if the id is unknown.
            InvalidTransition: if the model is already retired.
        """
        _check_forbidden(model_id)
        return self._transition(model_id, "retired")

    def get(self, model_id: str) -> ModelInfo:
        """Return metadata for a specific model id.

        Raises:
            ForbiddenModelId: for ``latest`` and its equivalents, which R-68
                forbids. This is not a missing model and is reported differently.
            ModelNotLoaded: naming the id that is not resident.
        """
        _check_forbidden(model_id)
        try:
            return self._models[model_id]
        except KeyError:
            raise ModelNotLoaded(
                f"model {model_id!r} is not loaded; registered: {sorted(self._models) or 'none'}"
            ) from None

    def active(self, kind: ModelKind) -> ModelInfo | None:
        """Return the active model of a kind, or ``None`` if there isn't one."""
        for info in self._models.values():
            if info.kind == kind and info.status == "active":
                return info
        return None

    def verify(self, model_id: str, artifact: str | Path) -> bool:
        """Whether the artifact on disk still matches what was registered.

        This is what makes content addressing worth storing: an id whose bytes
        have changed since registration is a tampered or mis-deployed artifact,
        and the registry can say so instead of serving it.

        Raises:
            ModelNotLoaded: if the id is unknown.
            FileNotFoundError: if the artifact is missing.
        """
        info = self.get(model_id)
        return content_address(artifact) == info.sha256

    def snapshot(self) -> list[ModelInfo]:
        """Return all registered models, ordered by load time."""
        return sorted(self._models.values(), key=lambda info: info.loaded_at)


def now_utc() -> datetime:
    """Return the current UTC time. Isolated so tests can control it."""
    return datetime.now(UTC)
