r"""Tests for hyperparameter search (T-215, R-71).

The property under test is that tuning cannot reach the test split. The most
important test is therefore the structural one: :func:`search` has no parameter
through which test data could be passed. A discipline note would hold only as long
as nobody is in a hurry.
"""

from __future__ import annotations

import inspect

import pytest
from aegis_ml.training.pipeline import TrainingConfig
from aegis_ml.training.search import (
    DEFAULT_METRIC,
    SEARCH_METRICS,
    SearchError,
    SearchReport,
    Trial,
    final_test_evaluation,
    grid_configs,
    search,
)


class TestTheTestSplitIsUnreachable:
    """R-71's first half, enforced by the signature rather than by a note."""

    def test_search_takes_no_test_parameter(self) -> None:
        parameters = set(inspect.signature(search).parameters)

        assert not any("test" in name for name in parameters)

    def test_search_takes_exactly_the_two_tuning_folds(self) -> None:
        """Training and validation, and no third fold by another name."""
        parameters = set(inspect.signature(search).parameters)

        assert {"train_seq", "train_y", "valid_seq", "valid_y"} <= parameters
        assert not parameters & {"holdout_seq", "holdout_y", "eval_seq", "eval_y"}

    def test_the_report_claims_no_test_use(self) -> None:
        trial = Trial(config=TrainingConfig(), score=0.5, final_loss=0.1)
        report = SearchReport(
            metric="roc_auc", grid={}, trials=(trial,), best=trial, train_windows=1, valid_windows=1
        )

        payload = report.as_json()

        assert payload["test_split_used"] is False
        assert payload["rule"] == "R-71"
        assert not any("test" in str(key) and key != "test_split_used" for key in payload)

    def test_the_final_evaluation_is_a_separate_named_step(self) -> None:
        """The one permitted look at test has its own function, not a flag."""
        assert final_test_evaluation is not search
        assert "test_seq" in inspect.signature(final_test_evaluation).parameters


class TestGridExpansion:
    """The grid is deterministic, because an unreproducible search cannot be audited."""

    def test_expands_the_full_product(self) -> None:
        configs = grid_configs(TrainingConfig(), {"epochs": [1, 2], "nhead": [4, 8]})

        assert len(configs) == 4
        assert {(config.epochs, config.nhead) for config in configs} == {
            (1, 4),
            (1, 8),
            (2, 4),
            (2, 8),
        }

    def test_unvaried_knobs_come_from_the_base(self) -> None:
        base = TrainingConfig(learning_rate=0.05, d_model=64)

        configs = grid_configs(base, {"epochs": [1, 2]})

        assert all(config.learning_rate == 0.05 for config in configs)
        assert all(config.d_model == 64 for config in configs)

    def test_expansion_order_is_deterministic(self) -> None:
        grid = {"epochs": [1, 2, 3], "nhead": [4, 8]}
        first = grid_configs(TrainingConfig(), grid)
        second = grid_configs(TrainingConfig(), grid)

        assert [config.model_dump() for config in first] == [
            config.model_dump() for config in second
        ]

    def test_a_single_value_grid_is_allowed(self) -> None:
        assert len(grid_configs(TrainingConfig(), {"epochs": [4]})) == 1

    def test_every_config_is_a_valid_training_config(self) -> None:
        configs = grid_configs(TrainingConfig(), {"dropout": [0.0, 0.5], "batch_size": [8, 16]})

        assert all(isinstance(config, TrainingConfig) for config in configs)


class TestGridRefusals:
    """A search over unrecorded knobs is not reproducible, so it does not run."""

    def test_an_empty_grid_is_refused(self) -> None:
        with pytest.raises(SearchError, match="grid is empty"):
            grid_configs(TrainingConfig(), {})

    def test_an_unknown_knob_is_refused(self) -> None:
        with pytest.raises(SearchError, match="not TrainingConfig fields"):
            grid_configs(TrainingConfig(), {"learning_rate": [1e-3], "vibes": [1, 2]})

    def test_a_knob_with_no_values_is_refused(self) -> None:
        with pytest.raises(SearchError, match="no values for"):
            grid_configs(TrainingConfig(), {"epochs": [1], "nhead": []})

    def test_an_invalid_combination_is_refused_rather_than_skipped(self) -> None:
        """Silently dropping an unusable value would hide a gap in the grid.

        ``dropout`` is bounded below 1.0 by the config model. Note that
        ``d_model``/``nhead`` divisibility is *not* caught here: the config model
        does not validate it, so an incompatible pair surfaces later when the torch
        model is built. That is a real gap, but it belongs to the config model
        rather than to the grid expansion.
        """
        with pytest.raises(SearchError, match="not a valid TrainingConfig"):
            grid_configs(TrainingConfig(), {"dropout": [1.5]})


class TestSearchRefusals:
    """Bad inputs fail loudly instead of producing a plausible ranking."""

    def test_an_unknown_metric_is_refused(self) -> None:
        with pytest.raises(SearchError, match="not a selection metric"):
            search(
                [[[0.0]]], [True], [[[0.0]]], [False], grid_values={"epochs": [1]}, metric="vibes"
            )

    def test_the_default_metric_is_a_known_one(self) -> None:
        assert DEFAULT_METRIC in SEARCH_METRICS

    def test_an_empty_training_fold_is_refused(self) -> None:
        with pytest.raises(SearchError, match="non-empty"):
            search([], [], [[0.0]], [False], grid_values={"epochs": [1]})

    def test_an_empty_validation_fold_is_refused(self) -> None:
        with pytest.raises(SearchError, match="non-empty"):
            search([[[0.0]]], [True], [], [], grid_values={"epochs": [1]})


class TestSearchRun:
    """The search itself. Needs torch, so skipped without it."""

    @pytest.fixture(autouse=True)
    def _needs_torch(self) -> None:
        pytest.importorskip("torch")

    #: train() takes a sequence of windows, each a sequence of feature vectors --
    #: not a sequence of flat rows. The shape is the thing that is easy to get
    #: wrong here, so it is named rather than inlined.
    _STEPS = 5
    _WIDTH = 2

    def _windows(self, count: int, modulus: int) -> list[list[list[float]]]:
        return [
            [
                [float((i + step) % modulus) / modulus for _ in range(self._WIDTH)]
                for step in range(self._STEPS)
            ]
            for i in range(count)
        ]

    def _folds(
        self,
    ) -> tuple[list[list[list[float]]], list[bool], list[list[list[float]]], list[bool]]:
        train_x = self._windows(24, 7)
        train_y = [i % 4 == 0 for i in range(24)]
        valid_x = self._windows(20, 5)
        valid_y = [i % 3 == 0 for i in range(20)]
        return train_x, train_y, valid_x, valid_y

    def test_every_configuration_is_tried_and_logged(self) -> None:
        train_x, train_y, valid_x, valid_y = self._folds()

        report = search(
            train_x,
            train_y,
            valid_x,
            valid_y,
            grid_values={"epochs": [1, 2], "nhead": [4, 8]},
            base=TrainingConfig(d_model=32, dim_feedforward=32, seed=20260114),
        )

        assert len(report.trials) == 4
        assert report.train_windows == 24
        assert report.valid_windows == 20

    def test_the_best_trial_is_the_highest_scoring_one(self) -> None:
        train_x, train_y, valid_x, valid_y = self._folds()

        report = search(
            train_x,
            train_y,
            valid_x,
            valid_y,
            grid_values={"epochs": [1, 2], "nhead": [4, 8]},
            base=TrainingConfig(d_model=32, dim_feedforward=32, seed=20260114),
        )

        assert report.best.score == max(trial.score for trial in report.trials)
        assert report.best in report.trials

    def test_every_trial_logs_its_complete_config(self) -> None:
        """Two configs differing only in an unlogged field would be indistinguishable."""
        train_x, train_y, valid_x, valid_y = self._folds()

        report = search(
            train_x,
            train_y,
            valid_x,
            valid_y,
            grid_values={"dropout": [0.0, 0.4]},
            base=TrainingConfig(d_model=32, dim_feedforward=32, nhead=4, seed=7),
        )
        payloads = [trial.as_json() for trial in report.trials]

        assert {payload["config"]["dropout"] for payload in payloads} == {0.0, 0.4}
        for payload in payloads:
            assert payload["config"]["d_model"] == 32
            assert payload["config"]["seed"] == 7
            assert set(payload["config"]) == set(TrainingConfig.model_fields)

    def test_the_callback_sees_progress(self) -> None:
        train_x, train_y, valid_x, valid_y = self._folds()
        seen: list[tuple[int, int]] = []

        search(
            train_x,
            train_y,
            valid_x,
            valid_y,
            grid_values={"epochs": [1, 2, 3]},
            base=TrainingConfig(d_model=32, dim_feedforward=32, nhead=4, seed=7),
            on_trial=lambda trial, index, total: seen.append((index, total)),
        )

        assert seen == [(1, 3), (2, 3), (3, 3)]

    def test_the_report_serialises_with_the_grid_and_the_winner(self) -> None:
        train_x, train_y, valid_x, valid_y = self._folds()

        payload = search(
            train_x,
            train_y,
            valid_x,
            valid_y,
            grid_values={"epochs": [1, 2]},
            base=TrainingConfig(d_model=32, dim_feedforward=32, nhead=4, seed=7),
        ).as_json()

        assert payload["grid"] == {"epochs": [1, 2]}
        assert payload["trial_count"] == 2
        assert payload["selection_metric"] == DEFAULT_METRIC
        assert payload["test_split_used"] is False
        assert "best_config" in payload

    def test_the_same_grid_and_seed_reproduce_the_same_scores(self) -> None:
        """An unreproducible search cannot be audited, so it must be deterministic."""
        train_x, train_y, valid_x, valid_y = self._folds()
        kwargs = {
            "grid_values": {"epochs": [2]},
            "base": TrainingConfig(d_model=32, dim_feedforward=32, nhead=4, seed=99),
        }

        first = search(train_x, train_y, valid_x, valid_y, **kwargs)  # type: ignore[arg-type]
        second = search(train_x, train_y, valid_x, valid_y, **kwargs)  # type: ignore[arg-type]

        assert first.best.score == pytest.approx(second.best.score, abs=1e-9)

    def test_final_test_evaluation_returns_a_recorded_result(self) -> None:
        train_x, train_y, valid_x, valid_y = self._folds()

        result = final_test_evaluation(
            TrainingConfig(d_model=32, dim_feedforward=32, nhead=4, epochs=1, seed=7),
            train_x,
            train_y,
            valid_x,
            valid_y,
        )

        assert result["rule"] == "R-71"
        assert result["test_windows"] == 20
        assert "report" in result

    def test_final_test_evaluation_refuses_an_empty_fold(self) -> None:
        with pytest.raises(SearchError, match="non-empty"):
            final_test_evaluation(TrainingConfig(), [], [], [[[0.0]]], [True])
