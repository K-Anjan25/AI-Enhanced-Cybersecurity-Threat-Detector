from app.utils.helpers import severity_to_score, score_to_severity


def test_severity_to_score_mapping():
    assert severity_to_score("CRITICAL") == 0.95
    assert severity_to_score("HIGH") == 0.75
    assert severity_to_score("MEDIUM") == 0.5
    assert severity_to_score("LOW") == 0.2
    assert severity_to_score("unknown") == 0.1


def test_score_to_severity_network():
    """Network scores share the ml-service 0..1 contract (higher = worse).

    The ml-service normalizes the IsolationForest decision score to 0..1
    before returning it, so network severities use the same bands as log.
    """
    assert score_to_severity(0.95, "network") == "CRITICAL"
    assert score_to_severity(0.8, "network") == "HIGH"
    assert score_to_severity(0.5, "network") == "MEDIUM"
    assert score_to_severity(0.1, "network") == "LOW"


def test_score_to_severity_log():
    assert score_to_severity(0.1, "log") == "LOW"
    assert score_to_severity(0.5, "log") == "MEDIUM"
    assert score_to_severity(0.8, "log") == "HIGH"
    assert score_to_severity(0.95, "log") == "CRITICAL"
