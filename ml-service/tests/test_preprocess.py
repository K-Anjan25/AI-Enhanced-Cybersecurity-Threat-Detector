"""Tests for preprocessing (T-105).

The numbers asserted here are computed by hand, not read back from the
implementation: for the column [1, 2, 3, 4] the mean is 2.5 and the population
standard deviation is sqrt(1.25), so a value of 4 standardises to
1.5 / sqrt(1.25).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from aegis_ml.data.preprocess import (
    UNKNOWN_INDEX,
    Preprocessor,
    StandardScaler,
    Vocabulary,
    redact,
)

KEY = b"0123456789abcdef0123456789abcdef"


def test_scaler_matches_hand_computed_statistics() -> None:
    scaler = StandardScaler.fit([[1.0], [2.0], [3.0], [4.0]], ["x"])
    assert scaler.means == (2.5,)
    assert scaler.stds[0] == pytest.approx(math.sqrt(1.25))
    assert scaler.transform([4.0])[0] == pytest.approx(1.5 / math.sqrt(1.25))
    assert scaler.transform([2.5])[0] == pytest.approx(0.0)


def test_scaler_handles_several_features_independently() -> None:
    scaler = StandardScaler.fit([[0.0, 10.0], [2.0, 10.0]], ["a", "b"])
    assert scaler.means == (1.0, 10.0)
    assert scaler.stds[0] == pytest.approx(1.0)


def test_zero_variance_feature_is_centred_not_divided_by_zero() -> None:
    """Every value equals the mean, so 0.0 is the informative result."""
    scaler = StandardScaler.fit([[5.0], [5.0], [5.0]], ["x"])
    assert scaler.stds == (0.0,)
    assert scaler.transform([5.0]) == [0.0]
    assert not math.isinf(scaler.transform([5.0])[0])


def test_scaler_refuses_ragged_rows() -> None:
    with pytest.raises(ValueError, match="row 1 has 1 values, expected 2"):
        StandardScaler.fit([[1.0, 2.0], [3.0]], ["a", "b"])


def test_scaler_refuses_zero_rows() -> None:
    with pytest.raises(ValueError, match="zero rows"):
        StandardScaler.fit([], ["a"])


def test_scaler_refuses_wrong_width_on_transform() -> None:
    scaler = StandardScaler.fit([[1.0]], ["a"])
    with pytest.raises(ValueError, match="expected 1 values, got 2"):
        scaler.transform([1.0, 2.0])


def test_vocabulary_reserves_index_zero_for_unknown() -> None:
    vocabulary = Vocabulary.fit(["tcp", "udp", "tcp"])
    assert vocabulary.values[UNKNOWN_INDEX] == ""
    assert vocabulary.values == ("", "tcp", "udp")


def test_vocabulary_is_sorted_so_runs_agree() -> None:
    first = Vocabulary.fit(["udp", "tcp", "icmp"])
    second = Vocabulary.fit(["icmp", "udp", "tcp"])
    assert first == second


def test_unseen_value_maps_to_unknown_without_shifting_indices() -> None:
    """A production model must score a protocol it has never seen."""
    vocabulary = Vocabulary.fit(["tcp", "udp"])
    assert vocabulary.encode("tcp") == 1
    assert vocabulary.encode("quic") == UNKNOWN_INDEX
    assert vocabulary.encode("udp") == 2


def test_redact_is_stable_and_keyed() -> None:
    first = redact("192.168.10.5", key=KEY)
    assert first == redact("192.168.10.5", key=KEY)
    assert first != redact("192.168.10.6", key=KEY)
    assert first != redact("192.168.10.5", key=b"x" * 32)


def test_redact_does_not_leak_the_address() -> None:
    pseudonym = redact("192.168.10.5", key=KEY)
    assert "192.168" not in pseudonym
    assert pseudonym != "192.168.10.5"


def test_redact_refuses_a_short_key() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        redact("192.168.10.5", key=b"short")


def test_preprocessor_round_trips_losslessly(tmp_path: Path) -> None:
    original = Preprocessor(
        scaler=StandardScaler.fit([[1.0, 2.0], [3.0, 4.0]], ["a", "b"]),
        vocabularies={"protocol": Vocabulary.fit(["tcp", "udp"])},
    )
    path = tmp_path / "preprocessor.json"
    original.save(str(path))
    restored = Preprocessor.load(str(path))
    assert restored == original
    assert restored.scaler.stds == original.scaler.stds
    assert restored.vocabularies["protocol"].values == ("", "tcp", "udp")


def test_preprocessor_save_is_deterministic(tmp_path: Path) -> None:
    """The same input must produce byte-identical artifacts (R-67)."""
    bundle = Preprocessor(
        scaler=StandardScaler.fit([[1.0], [2.0]], ["a"]),
        vocabularies={"protocol": Vocabulary.fit(["tcp"])},
    )
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    bundle.save(str(first))
    bundle.save(str(second))
    assert first.read_bytes() == second.read_bytes()
