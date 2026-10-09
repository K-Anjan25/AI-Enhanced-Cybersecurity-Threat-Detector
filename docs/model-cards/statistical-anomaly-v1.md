# Model Card: statistical-anomaly-v1

## Model Details

| Field            | Value                               |
| ---------------- | ----------------------------------- |
| **Model ID**     | statistical-anomaly-v1              |
| **Kind**         | flow                                |
| **Framework**    | Scikit-learn (IsolationForest)      |
| **Version**      | 1.0.0                               |
| **Status**       | active                              |
| **Artifact URI** | ml-service://statistical-anomaly-v1 |
| **SHA256**       | (recorded in model registry)        |

## Intended Use

- **Primary:** Detect anomalous network flow patterns indicating potential threats
- **Users:** Security analysts reviewing alerts in the AEGIS dashboard
- **Out of scope:** Log-based detection (separate model), real-time packet inspection

## Training Data

- **Source:** CICIDS2017 + synthetic network flow data
- **Size:** ~500,000 flow records
- **Features:** dst_port, proto, bytes_in, bytes_out, packets_in, packets_out, duration
- **Split:** 80% train, 10% validation, 10% test

## Metrics (on test split)

| Metric    | Value | Source                   |
| --------- | ----- | ------------------------ |
| Precision | 0.92  | runs/flownet/eval@2.json |
| Recall    | 0.87  | runs/flownet/eval@2.json |
| F1        | 0.89  | runs/flownet/eval@2.json |
| ROC AUC   | 0.95  | runs/flownet/eval@2.json |
| PR AUC    | 0.91  | runs/flownet/eval@2.json |

## Limitations

- Trained on predominantly TCP traffic; UDP/ICMP detection may be less accurate
- Does not inspect packet payloads (flow metadata only)
- May produce false positives for legitimate high-traffic services (CDN, video streaming)
- Drift detection monitors PSI; retraining recommended when PSI > 0.25

## Ethical Considerations

- Model does not use PII; only network metadata
- False positives may trigger unnecessary analyst review (time cost)
- False negatives may miss novel attack patterns

## Maintenance

- **Drift monitoring:** Continuous via `aegis_drift_psi{feature}` gauges
- **Retraining trigger:** PSI > 0.25 on any feature for > 24 hours
- **Feedback loop:** Analyst verdicts feed weekly threshold recalibration
- **Owner:** AEGIS ML team
