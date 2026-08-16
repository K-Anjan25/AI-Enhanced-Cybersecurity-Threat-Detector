# Project Documentation

Software-engineering documentation for the **AI-Enhanced Cybersecurity Threat Detector**
(v3 target: event-driven, multi-tenant, K8s-ready SOC platform).

## Index

| Document | Type | Contents |
| --- | --- | --- |
| [`functional-requirements.md`](functional-requirements.md) | FRS | Functional requirements (FR-xx) by module, MoSCoW priorities |
| [`non-functional-requirements.md`](non-functional-requirements.md) | NFRS | Non-functional requirements (NFR-xx) with measurable targets + verification |
| [`database-design.md`](database-design.md) | DB Design | ERD, table catalog, normalization analysis (1NF/2NF/3NF/BCNF), indexes |
| [`traceability-matrix.md`](traceability-matrix.md) | RTM | FR/NFR → implementation → tests mapping + coverage gaps |
| [`session-log.md`](session-log.md) | Process | Phase-by-phase build/hardening history, mapped to commits |
| [`ml-pipeline.md`](ml-pipeline.md) | ML Ops | Training→serving pipeline, scheduled retrain CronJob, model versioning, feature contract |
| [`../k8s/README.md`](../k8s/README.md) | Infra | Kubernetes manifests for backend, ml-service, training CronJob, dashboard, HPA, ingress |
| [`../diagrams/README.md`](../diagrams/README.md) | UML | Sequence, class, state, activity, timing, component, deployment diagrams |

## Related

- **Architecture:** [`diagrams/target-architecture.md`](../diagrams/target-architecture.md),
  [`diagrams/target-design.md`](../diagrams/target-design.md)
- **Process notes:** diagrams are generated from code and kept in sync on change
  (see `diagrams/README.md`); CI runs backend `pytest`, dashboard `tsc` + `vite build`.

## Conventions

- Requirement IDs are stable and referenced from tests/comments (`FR-AUTH-07`, `NFR-SEC-04`, …).
- Every new feature should add: an FR (or map to an existing one), a test reference in the
  traceability matrix, and a diagram update if the API surface or models change.
