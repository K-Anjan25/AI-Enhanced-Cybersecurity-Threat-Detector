"""MLflow-backed lifecycle for LogNet bundles: track, register, gate, promote, roll back.

The rules this module enforces, and where each one is checked:

* **Every run records its baseline.** The training metrics carry the severity
  rule's ROC-AUC on the same held-out windows (``baseline_severity_auc``). A
  candidate is never judged on its own numbers alone.
* **Promotion is gated.** :func:`evaluate_gate` must pass before
  :func:`promote` moves the ``champion`` alias. A failed gate is a refusal, not a
  warning.
* **Promotion re-checks the bytes.** The weights are downloaded from the tracking
  store and hashed again before the alias moves. A mismatch with the hash recorded
  at training time is refused. This is the content-address rule from
  :mod:`aegis_ml.registry.model_registry` (R-68), applied to MLflow.
* **Rollback is history, not a rewrite.** Each promotion records the version it
  replaced. :func:`rollback` moves the alias back along that record. Versions are
  never deleted or edited.

Serving reads the ``champion`` alias through :func:`fetch_champion`, which verifies
the hash the same way promotion does.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from aegis_ml.training.lognet_train import WEIGHTS_FILE

#: Registered-model name in MLflow.
MODEL_NAME = "aegis-lognet"
#: Alias that serving follows. Aliases are MLflow's replacement for stages.
CHAMPION_ALIAS = "champion"
#: Tag on a version: the version it replaced when it was promoted.
PREVIOUS_TAG = "aegis.previous_version"
#: Tag on a version: the sha256 of ``lognet.pt`` when the run was logged.
WEIGHTS_SHA_TAG = "aegis.weights_sha256"
#: Tag on a version: the sha256 of the training lines, for data lineage.
DATA_SHA_TAG = "aegis.data_sha256"
#: Tag on a version: the gate decision that allowed its promotion.
GATE_TAG = "aegis.gate"
#: Tag on a version: when it was last rolled back *from*.
ROLLED_BACK_TAG = "aegis.rolled_back_at"
#: Artifact directory inside each run that holds the bundle files.
BUNDLE_ARTIFACT = "bundle"


class LifecycleError(RuntimeError):
    """Base class for refusals made by the lifecycle."""


class GateRefused(LifecycleError):
    """Raised when a candidate does not pass the promotion gate."""


class IntegrityError(LifecycleError):
    """Raised when stored weights do not match the hash recorded at training time."""


class NothingToRollBack(LifecycleError):
    """Raised when there is no champion, or no recorded version to return to."""


@dataclass(frozen=True)
class GateConfig:
    """Thresholds a candidate must clear. Recorded with every decision."""

    #: Absolute floor on held-out ROC-AUC. Below this the model is not useful.
    min_roc_auc: float = 0.80
    #: Required margin over the severity baseline's ROC-AUC on the same windows.
    margin_over_baseline: float = 0.0


@dataclass(frozen=True)
class GateResult:
    """The outcome of :func:`evaluate_gate`, stored on the version it concerns."""

    passed: bool
    candidate_roc_auc: float | None
    baseline_roc_auc: float | None
    config: GateConfig
    reasons: list[str] = field(default_factory=list)

    def as_tag(self) -> str:
        """A compact JSON form for an MLflow tag."""
        return json.dumps(asdict(self), sort_keys=True)


def evaluate_gate(
    metrics: Mapping[str, Any], config: GateConfig = GateConfig()
) -> GateResult:
    """Decide whether a candidate's held-out metrics clear the gate.

    The candidate must (a) have a ROC-AUC, which needs both classes in the held-out
    windows, (b) reach ``min_roc_auc``, and (c) beat the severity baseline by at
    least ``margin_over_baseline``. Every failed condition is listed in ``reasons``.
    """
    candidate = _as_float(metrics.get("roc_auc"))
    baseline = _as_float(metrics.get("baseline_severity_auc"))
    reasons: list[str] = []
    if candidate is None:
        reasons.append("no held-out ROC-AUC: the held-out windows lack one class")
    elif candidate < config.min_roc_auc:
        reasons.append(f"ROC-AUC {candidate:.3f} is below the floor {config.min_roc_auc:.3f}")
    if baseline is None:
        reasons.append("no severity baseline ROC-AUC recorded for this run")
    elif candidate is not None and candidate < baseline + config.margin_over_baseline:
        reasons.append(
            f"ROC-AUC {candidate:.3f} does not beat the severity baseline "
            f"{baseline:.3f} by {config.margin_over_baseline:.3f}"
        )
    return GateResult(
        passed=not reasons,
        candidate_roc_auc=candidate,
        baseline_roc_auc=baseline,
        config=config,
        reasons=reasons,
    )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def sha256_file(path: Path) -> str:
    """The sha256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


# ── MLflow access ─────────────────────────────────────────────────────────────


def store_dir() -> Path:
    """Where tracking data lives by default. Outside the repository on purpose."""
    override = os.environ.get("AEGIS_MLFLOW_DIR")
    return Path(override) if override else Path.home() / ".aegis" / "mlflow"


def tracking_uri() -> str:
    """The tracking URI: ``AEGIS_MLFLOW_TRACKING_URI`` or a SQLite file in the store."""
    explicit = os.environ.get("AEGIS_MLFLOW_TRACKING_URI")
    if explicit:
        return explicit
    path = store_dir() / "mlflow.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.resolve()}"


def artifact_root() -> str:
    """Where run artifacts (the weights) are written."""
    explicit = os.environ.get("AEGIS_MLFLOW_ARTIFACT_ROOT")
    if explicit:
        return explicit
    root = store_dir() / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve().as_uri()


def client(uri: str | None = None) -> Any:
    """An MLflow client for the configured or given tracking URI."""
    from mlflow import MlflowClient  # noqa: PLC0415 - optional extra

    resolved = uri or tracking_uri()
    return MlflowClient(tracking_uri=resolved, registry_uri=resolved)


def _is_missing(exc: Exception) -> bool:
    return getattr(exc, "error_code", "") == "RESOURCE_DOES_NOT_EXIST"


def _alias_unset(exc: Exception) -> bool:
    text = str(exc).lower()
    return "alias" in text and "not found" in text


def _ensure_experiment(mlf: Any, name: str, root: str) -> str:
    existing = mlf.get_experiment_by_name(name)
    if existing is not None:
        return str(existing.experiment_id)
    return str(mlf.create_experiment(name, artifact_location=f"{root}/{name}"))


def _ensure_registered_model(mlf: Any, name: str) -> None:
    try:
        mlf.get_registered_model(name)
    except Exception as exc:
        if not _is_missing(exc):
            raise
        mlf.create_registered_model(name)


@dataclass(frozen=True)
class LoggedRun:
    """What :func:`log_run` produced."""

    run_id: str
    weights_sha256: str
    metrics: dict[str, Any]


def log_run(
    mlf: Any,
    bundle_dir: Path,
    *,
    experiment: str,
    data_sha256: str,
    run_name: str | None = None,
) -> LoggedRun:
    """Log a trained bundle as an MLflow run: its params, metrics and files.

    The bundle's ``lognet.json`` holds the metrics and the training config. The
    weights' sha256 is tagged on the run now, so later verification has something to
    compare against.
    """
    meta = json.loads((bundle_dir / "lognet.json").read_text(encoding="utf-8"))
    weights_sha = sha256_file(bundle_dir / WEIGHTS_FILE)
    experiment_id = _ensure_experiment(mlf, experiment, artifact_root())
    run = mlf.create_run(
        experiment_id,
        run_name=run_name or meta["model_id"],
        tags={WEIGHTS_SHA_TAG: weights_sha, DATA_SHA_TAG: data_sha256},
    )
    run_id = str(run.info.run_id)
    for key, value in meta["train_config"].items():
        mlf.log_param(run_id, f"train.{key}", value)
    metrics = {k: v for k, v in meta["metrics"].items() if isinstance(v, (int, float))}
    for key, value in metrics.items():
        mlf.log_metric(run_id, key, float(value))
    mlf.log_param(run_id, "model_id", meta["model_id"])
    mlf.log_param(run_id, "threshold", meta["threshold"])
    mlf.log_artifacts(run_id, str(bundle_dir), artifact_path=BUNDLE_ARTIFACT)
    mlf.set_terminated(run_id)
    return LoggedRun(run_id=run_id, weights_sha256=weights_sha, metrics=dict(meta["metrics"]))


def register_version(mlf: Any, run: LoggedRun, *, data_sha256: str, name: str = MODEL_NAME) -> str:
    """Register a logged run as a new version of the model. Returns the version number."""
    _ensure_registered_model(mlf, name)
    version = mlf.create_model_version(
        name,
        source=f"runs:/{run.run_id}/{BUNDLE_ARTIFACT}",
        run_id=run.run_id,
        tags={WEIGHTS_SHA_TAG: run.weights_sha256, DATA_SHA_TAG: data_sha256},
    )
    return str(version.version)


def champion(mlf: Any, name: str = MODEL_NAME) -> Any | None:
    """The version the ``champion`` alias points at, or ``None`` if there is none."""
    try:
        return mlf.get_model_version_by_alias(name, CHAMPION_ALIAS)
    except Exception as exc:
        # MLflow reports an unset alias as INVALID_PARAMETER_VALUE, not as a missing
        # resource, so the message is the only signal. Anything else is re-raised.
        if _is_missing(exc) or _alias_unset(exc):
            return None
        raise


def _verify_version(mlf: Any, version: Any, download_dir: Path) -> Path:
    """Download a version's weights and check them against the recorded hash."""
    expected = version.tags.get(WEIGHTS_SHA_TAG)
    if not expected:
        raise IntegrityError(f"version {version.version} has no recorded weights hash")
    local = Path(
        mlf.download_artifacts(version.run_id, f"{BUNDLE_ARTIFACT}/{WEIGHTS_FILE}", str(download_dir))
    )
    actual = sha256_file(local)
    if actual != expected:
        raise IntegrityError(
            f"version {version.version}: stored weights hash {actual[:12]}… does not match "
            f"the hash recorded at training time {expected[:12]}…. Refusing to serve."
        )
    return local


def promote(
    mlf: Any,
    version: str,
    gate: GateResult,
    *,
    name: str = MODEL_NAME,
    download_dir: Path,
) -> str | None:
    """Move the ``champion`` alias to ``version``. Returns the version it replaced.

    Refused when the gate did not pass or the stored weights fail verification.
    The replaced version is written onto the new one, so :func:`rollback` can
    return to it.
    """
    if not gate.passed:
        raise GateRefused("promotion refused: " + "; ".join(gate.reasons))
    target = mlf.get_model_version(name, version)
    _verify_version(mlf, target, download_dir)
    incumbent = champion(mlf, name)
    if incumbent is not None and str(incumbent.version) == str(version):
        return None  # already the champion: nothing to move
    previous = str(incumbent.version) if incumbent is not None else ""
    mlf.set_model_version_tag(name, version, GATE_TAG, gate.as_tag())
    mlf.set_model_version_tag(name, version, PREVIOUS_TAG, previous)
    mlf.set_registered_model_alias(name, CHAMPION_ALIAS, version)
    return previous or None


def rollback(mlf: Any, *, name: str = MODEL_NAME, download_dir: Path) -> str:
    """Move ``champion`` back to the version it replaced. Returns that version.

    The version being rolled back from is kept and tagged, so the history shows
    what was withdrawn and when.
    """
    current = champion(mlf, name)
    if current is None:
        raise NothingToRollBack("there is no champion to roll back from")
    previous = str(current.tags.get(PREVIOUS_TAG, ""))
    if not previous:
        raise NothingToRollBack(f"version {current.version} has no earlier version to return to")
    restored = mlf.get_model_version(name, previous)
    _verify_version(mlf, restored, download_dir)
    from datetime import UTC, datetime  # noqa: PLC0415

    mlf.set_model_version_tag(
        name, str(current.version), ROLLED_BACK_TAG, datetime.now(UTC).isoformat()
    )
    mlf.set_registered_model_alias(name, CHAMPION_ALIAS, previous)
    return previous


def fetch_champion(mlf: Any, dest: Path, *, name: str = MODEL_NAME) -> Path:
    """Download the champion bundle into ``dest``, verified. Serving calls this.

    Returns the directory to point ``AEGIS_LOGNET_BUNDLE_DIR`` at.
    """
    current = champion(mlf, name)
    if current is None:
        raise NothingToRollBack(f"no champion is set for {name!r}")
    dest.mkdir(parents=True, exist_ok=True)
    weights = _verify_version(mlf, current, dest / ".download")
    bundle = dest / str(current.version)
    bundle.mkdir(parents=True, exist_ok=True)
    weights.replace(bundle / WEIGHTS_FILE)
    meta = Path(
        mlf.download_artifacts(current.run_id, f"{BUNDLE_ARTIFACT}/lognet.json", str(dest / ".download"))
    )
    (bundle / "lognet.json").write_bytes(meta.read_bytes())
    return bundle
