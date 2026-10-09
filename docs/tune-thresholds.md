# AEGIS Threshold Tuning Guide

## Overview

AEGIS uses thresholds at multiple stages. Tuning them trades off precision vs recall.

## Detection Thresholds

### Rule-Based Detector (backend/app/services/rule_detector.py)

| Rule | Default Threshold | Description |
|------|-------------------|-------------|
| Port scan | >10 unique ports/min from one source | Detects horizontal scanning |
| High-volume transfer | >100MB in 5 min from one source | Detects data exfiltration |
| Brute force | >20 failed auth/min from one source | Detects password attacks |
| DNS tunneling | >500 DNS queries/min from one source | Detects DNS-based C2 |

**To adjust:** Edit `backend/app/services/rule_detector.py` constants.

### ML Scoring (ml-service/aegis_ml/)

| Threshold | Default | Effect |
|-----------|---------|--------|
| Anomaly score | 0.7 | Flows above this are flagged as anomalous |
| Alert creation | 0.85 | Only scores above this create alerts |
| Severity escalation | 0.95 | Scores above this are `critical` |

**To adjust:** Edit `ml-service/aegis_ml/serving/config.py` or environment variables.

## Drift Thresholds (FR-32)

| PSI Range | Interpretation | Action |
|-----------|----------------|--------|
| 0.00 – 0.10 | Stable | No action |
| 0.10 – 0.25 | Moderate drift | Monitor closely |
| > 0.25 | Significant drift | Retrain model |

The dashboard Drift page shows PSI per feature. When any feature exceeds 0.25, consider retraining.

## Alert Severity Mapping

| Score Range | Severity | Response |
|-------------|----------|----------|
| 0.85 – 0.90 | Low | Log, review in dashboard |
| 0.90 – 0.95 | Medium | Notify analyst |
| 0.95 – 0.99 | High | Page on-call responder |
| > 0.99 | Critical | Immediate escalation |

## Tuning Process

1. **Collect baseline**: Run for 1 week with default thresholds
2. **Review false positives**: Check alerts that analysts closed as benign
3. **Adjust**: Raise threshold if FP rate > 20%; lower if missed threats detected
4. **Validate**: Run for another week, compare metrics
5. **Document**: Record all changes in the runbook with rationale

## Feedback Loop

Analyst verdicts (true positive / false positive) are written back to the database. Weekly threshold recalibration uses this feedback to suggest optimal thresholds.
