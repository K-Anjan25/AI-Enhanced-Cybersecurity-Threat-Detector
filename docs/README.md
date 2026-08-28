# Project Documentation

Software-engineering documentation for the **AI-Enhanced Cybersecurity Threat Detector**
(v3 target: event-driven, multi-tenant, K8s-ready SOC platform).

## Index

| Document | Type | Contents |
| --- | --- | --- |
| [`demo.md`](demo.md) | Demo | 5-minute walkthrough script + route-by-route **verification matrix** (route → source file → endpoints → expected state) |
| [`noctra-redesign-spec.md`](noctra-redesign-spec.md) | Spec | Product model, IA, terminology, roadmap — **§40 is the current SIGNAL design system**; §9/§12–§17 are retired predecessors |
| [`brand-strategy.md`](brand-strategy.md) | Brand | Naming research + shortlist (NOCTRA decision record) |
| [`terminology-playbook.md`](terminology-playbook.md) | UX Writing | Jargon dogfooding rules + the term dictionary |
| [`noctra-qa-report.md`](noctra-qa-report.md) | QA | Full-route frontend audit findings |
| [`wireframes/`](wireframes/) | Wireframes | Code-accurate HTML wireframe kit — every route in the dashboard mapped 1:1 (open `wireframes/index.html`) |
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

## Test suites

| Suite | Command | Count |
| --- | --- | --- |
| Backend (pytest) | `cd backend && pytest tests` | 136 passed, 2 skipped |
| ML service (pytest) | `cd ml-service && pytest tests` | 13 passed |
| Dashboard (Vitest) | `cd dashboard && npm run test:ci` | 14 passed |

CI runs all three on every push, plus `tsc --noEmit` + `vite build` for the
dashboard and the k6 load-test suite.
