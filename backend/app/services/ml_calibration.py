"""The adapter over the ML package's calibrator (T-322, T-207).

The backend image does not install ``ml-service`` (D-037), so the arithmetic that
turns a benign sample into a threshold -- the quantile fit and the guardrail that
limits how far one run may move -- lives in ``aegis_ml.scoring.thresholds`` and is
reached through here. This is the same arrangement ``app.workers.scoring_worker``
has with ``aegis_ml.data.windowing``, and the same one ``app.pipeline`` documents:
one implementation of the arithmetic, and the service that needs it is handed it.

The import is inside :func:`_thresholds` rather than at module scope for one
reason: a deployment that installs the backend alone must still *start*, and must
fail at the call with a message naming the missing package rather than at import
with a traceback. Recalibrating thresholds is a route an operator invokes; it is
not on the ingest path, so refusing it is better than refusing to boot. It is
``importlib.import_module`` rather than an ``import`` statement for the same
reason, and because a static import would also need a suppression comment in one
of the two mypy configurations this repository runs.

``_Thresholds`` is the slice of that module this backend depends on, written down
as a protocol because ``aegis_ml`` ships no type marker: without it every value
read across the boundary would be ``Any`` and the adapter's own annotations would
describe nothing. The protocol is also the contract -- three names and no more --
so a change on the ML side that this file would not survive is a mypy error rather
than a runtime surprise in a weekly job.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Protocol, cast

from app.services.recalibration import Calibration

__all__ = ["CalibratorUnavailable", "MlCalibrator"]


class CalibratorUnavailable(RuntimeError):
    """The ML package is not installed, so T-207's calibrator cannot be reached."""


class _Change(Protocol):
    """The fields T-207's ``ThresholdChange`` carries."""

    previous: float
    requested: float
    applied: float
    clamped: bool
    quantile: float
    sample_size: int


class _Thresholds(Protocol):
    """The ML threshold module, as far as this backend uses it."""

    #: The quantile a fit is taken at -- T-207's target false-positive rate.
    DEFAULT_QUANTILE: float

    def fit_threshold(self, benign_scores: Sequence[float], *, quantile_: float) -> float:
        """Fit a threshold on benign traffic only."""
        ...

    def calibrate(
        self,
        key: str,
        requested: float,
        *,
        previous: float,
        quantile_: float,
        sample_size: int,
    ) -> _Change:
        """Clamp ``requested`` to within the guardrail of ``previous``."""
        ...


def _thresholds() -> _Thresholds:
    """The ML package's threshold module.

    Raises:
        CalibratorUnavailable: if ``aegis_ml`` is not importable, naming the
            install and the alternative (inject a ``Calibrator``).
    """
    try:
        # importlib, not a static import: the name is resolved when a run needs
        # the calibrator, and the file carries no import of a package that the
        # backend's own dependency list does not name.
        module = importlib.import_module("aegis_ml.scoring.thresholds")
    except ImportError as exc:
        msg = (
            "the recalibration job needs T-207's calibrator, but aegis_ml is not "
            "installed in this deployment; install ml-service "
            "(pip install -e ml-service) or inject a Calibrator"
        )
        raise CalibratorUnavailable(msg) from exc
    return cast(_Thresholds, module)


class MlCalibrator:
    """T-207's ``fit_threshold`` and ``calibrate``, behind the backend's protocol.

    No numbers are repeated here. The quantile comes from the ML module's own
    ``DEFAULT_QUANTILE``, and the guardrail is deliberately *not* passed to
    ``calibrate`` -- leaving it to that function's default is what makes T-207 the
    one place the 0.10 lives, so a backend change cannot widen the guardrail the
    acceptance criterion is about.
    """

    @property
    def quantile(self) -> float:
        """The quantile a fit is taken at, as the ML package documents it."""
        return float(_thresholds().DEFAULT_QUANTILE)

    def fit(self, scores: Sequence[float]) -> float:
        """The threshold these benign scores imply, before any clamping.

        Raises:
            ValueError: if the sample is empty or holds a score outside ``[0, 1]``
                -- propagated from the ML implementation, which refuses both.
        """
        return float(_thresholds().fit_threshold(scores, quantile_=self.quantile))

    def clamp(
        self, key: str, requested: float, *, previous: float, sample_size: int
    ) -> Calibration:
        """``requested``, limited to what one run is allowed to move (T-207)."""
        change = _thresholds().calibrate(
            key,
            requested,
            previous=previous,
            quantile_=self.quantile,
            sample_size=sample_size,
        )
        return Calibration(
            previous=float(change.previous),
            requested=float(change.requested),
            applied=float(change.applied),
            clamped=bool(change.clamped),
            quantile=float(change.quantile),
            sample_size=int(change.sample_size),
        )
