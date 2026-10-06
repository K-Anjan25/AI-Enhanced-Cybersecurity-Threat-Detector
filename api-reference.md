# AEGIS API reference

> Generated from the application's Pydantic schemas by
> `scripts/generate_api_reference.py`; do not edit by hand. CI renders this
> document again and fails when the two differ (T-320, D-054).

**AEGIS Backend** — API version `0.1.0`. Every request and response named below is a
Pydantic schema in `backend/app/schemas/`, and every path is one the application
actually serves.

## Authentication

One credential per request (R-53, FR-44): a bearer token as
`Authorization: Bearer <token>`, or an issued API key as `X-API-Key: <key>` or as a
bearer token. The roles column is the route matrix `test_rbac.py` asserts is
complete, so a route cannot be added without one.

Every operation answers `422` with `HTTPValidationError` when its query parameters
or body do not match the schema below.

## Routes

| Method | Path | Summary | Roles | Success | Request body |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/alerts` | Query alerts within a time window | admin, analyst, responder, viewer | `200` `AlertPage` | — |
| `GET` | `/api/v1/alerts/notifications` | Alerts published after a stream cursor (FR-20 fallback) | admin, analyst, responder, viewer | `200` `AlertNotificationsOut` | — |
| `GET` | `/api/v1/alerts/stream` | Server-Sent Events alert stream (FR-20 fallback) | admin, analyst, responder, viewer | `200` `text/event-stream` | — |
| `GET` | `/api/v1/alerts/{alert_id}` | Read one alert with its explanation, evidence, verdict and context (FR-51) | admin, analyst, responder, viewer | `200` `AlertDetailOut` | — |
| `POST` | `/api/v1/alerts/{alert_id}/verdict` | Record an analyst verdict on an alert (FR-16) | admin, analyst, responder | `200` `VerdictOutcomeOut` | `VerdictRequest` |
| `GET` | `/api/v1/alerts/{alert_id}/verdicts` | Read an alert's verdict history, oldest first (FR-16, FR-18) | admin, analyst, responder, viewer | `200` `VerdictHistoryOut` | — |
| `GET` | `/api/v1/audit` | Read the audit trail, newest first (FR-42) | admin, analyst, responder, viewer | `200` `AuditPageOut` | — |
| `POST` | `/api/v1/ingest/flows` | Ingest flow records (flow@1) | admin, analyst, responder | `200` `IngestResponse` | `FlowRecordIn` |
| `POST` | `/api/v1/ingest/logs` | Ingest log lines (log@1) | admin, analyst, responder | `200` `IngestResponse` | `LogRecordIn` |
| `GET` | `/api/v1/keys` | List API keys (FR-44) | admin | `200` `ApiKeyListOut` | — |
| `POST` | `/api/v1/keys` | Issue an API key (FR-44) | admin | `201` `ApiKeyIssuedOut` | `ApiKeyCreate` |
| `GET` | `/api/v1/keys/scopes` | List the scopes a key may hold (FR-44) | admin | `200` `ScopeListOut` | — |
| `DELETE` | `/api/v1/keys/{key_id}` | Revoke an API key (FR-44) | admin | `200` `ApiKeyOut` | — |
| `GET` | `/api/v1/models` | List registered model versions (FR-30) | admin, analyst, responder, viewer | `200` `ModelListOut` | — |
| `POST` | `/api/v1/models/{kind}/rollback` | Reverse the most recent promotion of a kind (FR-33) | admin | `200` `ModelTransitionOut` | `RollbackRequest` |
| `GET` | `/api/v1/models/{model_id}/metrics` | Held-out evaluation metrics for one version (FR-31) | admin, analyst, responder, viewer | `200` `ModelMetricsOut` | — |
| `POST` | `/api/v1/models/{model_id}/promote` | Make a version active and retire the incumbent (FR-33) | admin | `200` `ModelTransitionOut` | `PromotionRequest` |
| `POST` | `/api/v1/privacy/erasure` | Erase one data subject across every store (NFR-05, R-37) | admin | `200` `ErasureReportOut` | `ErasureRequest` |
| `GET` | `/api/v1/privacy/erasures` | The erasure ledger, newest first (NFR-05) | admin | `200` `ErasureLedgerPageOut` | — |
| `GET` | `/api/v1/retention` | Retention policy and the plan a run would execute (NFR-05) | admin | `200` `RetentionPlanOut` | — |
| `POST` | `/api/v1/retention/run` | Apply the retention plan (NFR-05) | admin | `200` `RetentionRunOut` | — |
| `GET` | `/api/v1/thresholds` | Thresholds in force, and the FR-13 defaults behind them (R-69) | admin, analyst, responder, viewer | `200` `ThresholdListOut` | — |
| `POST` | `/api/v1/thresholds/recalibrate` | Recalibrate a band from analyst verdicts, under T-207's guardrail (FR-18) | admin | `200` `RecalibrationOut` | `RecalibrationRequest` |
| `GET` | `/api/v1/webhooks` | List registered webhooks, without secrets | admin, responder | `200` `WebhookListOut` | — |
| `POST` | `/api/v1/webhooks` | Register an outbound webhook (FR-21) | admin, responder | `201` `WebhookCreatedOut` | `WebhookCreate` |
| `DELETE` | `/api/v1/webhooks/{webhook_id}` | Delete a webhook | admin, responder | `204` | — |
| `GET` | `/healthz` | Liveness probe | unauthenticated | `200` `HealthResponse` | — |
| `GET` | `/metrics` | Prometheus metrics | unauthenticated | `200` `text/plain` | — |
| `GET` | `/readyz` | Readiness probe | unauthenticated | `200` `ReadinessResponse` | — |

## Schemas

### `AlertDetailOut`

Everything design.md §4.3's four zones render, in one response.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `alert` | `AlertRow` | yes | — |
| `models` | `AlertModelsOut` | no | — |
| `explanation` | `ExplanationOut` | yes | — |
| `evidence` | `EvidenceOut` | yes | — |
| `verdict` | `AlertVerdictOut` | no | — |
| `related` | `RelatedAlertsOut` | yes | — |
| `family_history` | `FamilyHistoryOut` | yes | — |

### `AlertModelsOut`

The model versions that scored this alert, when the row recorded them.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `flow` | `string` or `null` | no | Pinned flow-model version, e.g. flownet@1.4.2. |
| `log` | `string` or `null` | no | Pinned log-model version. |

### `AlertNotificationOut`

One alert plus its stream position.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `sequence` | `integer` | yes | — |
| `alert` | `AlertRow` | yes | — |

### `AlertNotificationsOut`

The polling fallback, and what a client gets when it must resync.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `AlertNotificationOut` | yes | — |
| `oldest_available` | `integer` or `null` | yes | — |
| `latest` | `integer` or `null` | yes | — |
| `resync_required` | `boolean` | yes | — |
| `epoch` | `string` | yes | — |

### `AlertPage`

A page of alerts plus the cursor for the next one.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `AlertRow` | yes | — |
| `next_cursor` | `string` or `null` | yes | — |
| `limit` | `integer` | yes | — |
| `order` | `desc` or `asc` | yes | — |

### `AlertRow`

One alert as returned by the API.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `integer` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `entity_id` | `integer` | yes | — |
| `family` | `string` | yes | — |
| `severity` | `string` | yes | — |
| `score` | `number` | yes | — |
| `status` | `string` | yes | — |
| `first_seen` | `string (date-time)` | yes | — |
| `last_seen` | `string (date-time)` | yes | — |
| `occurrence_count` | `integer` | yes | — |
| `trace_id` | `string` or `null` | no | — |

### `AlertVerdictOut`

The alert's verdict history, oldest first, and the current one.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `current` | `VerdictRecordOut` or `null` | no | — |
| `history` | `VerdictRecordOut` | no | — |

### `ApiKeyCreate`

A key to issue.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` | yes | — |
| `scopes` | list of `string` | yes | — |

### `ApiKeyIssuedOut`

A newly issued key, with its secret shown exactly once.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `integer` | yes | — |
| `name` | `string` | yes | — |
| `prefix` | `string` | yes | — |
| `owner` | `string` | yes | — |
| `scopes` | list of `string` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `last_used_at` | `string (date-time)` or `null` | yes | — |
| `revoked_at` | `string (date-time)` or `null` | yes | — |
| `secret` | `string` | yes | The API key. Shown once; store it now. |

### `ApiKeyListOut`

Every key, revoked ones included, so the list is the record of what existed.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `ApiKeyOut` | yes | — |

### `ApiKeyOut`

An issued key, **without** its secret.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `integer` | yes | — |
| `name` | `string` | yes | — |
| `prefix` | `string` | yes | — |
| `owner` | `string` | yes | — |
| `scopes` | list of `string` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `last_used_at` | `string (date-time)` or `null` | yes | — |
| `revoked_at` | `string (date-time)` or `null` | yes | — |

### `AuditAction`

The actions the trail records, one per mutating route.

Types: `ingest.flows` or `ingest.logs` or `alert.verdict` or `webhook.create` or `webhook.delete` or `key.create` or `key.revoke` or `retention.apply` or `privacy.erasure` or `model.promote` or `model.rollback` or `threshold.recalibrate`.

### `AuditEntryOut`

One recorded action.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `integer` | yes | Trail sequence, 1-based and monotonic. |
| `actor` | `string` | yes | The principal the access token named. |
| `action` | `string` | yes | — |
| `target_type` | `string` | yes | — |
| `target_id` | `string` | yes | — |
| `detail` | `object` | yes | — |
| `ip` | `string` or `null` | yes | — |
| `at` | `string (date-time)` | yes | — |

### `AuditPageOut`

A page of the trail, newest first.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `AuditEntryOut` | yes | — |
| `next_before` | `integer` or `null` | yes | — |

### `Direction`

Traffic direction relative to the monitored boundary.

Types: `inbound` or `outbound` or `internal`.

### `DroppedPartitionOut`

One monthly partition, with the span it covers.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `table` | `string` | yes | — |
| `name` | `string` | yes | — |
| `year` | `integer` | yes | — |
| `month` | `integer` | yes | — |
| `covers_start` | `string (date)` | yes | — |
| `covers_end` | `string (date)` | yes | — |
| `statement` | `string` | yes | — |

### `ErasureLedgerEntryOut`

One recorded erasure.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `sequence` | `integer` | yes | — |
| `tombstone` | `string` | yes | — |
| `kind` | `string` | yes | — |
| `at` | `string (date-time)` | yes | — |
| `requested_by` | `string` | yes | — |
| `targets` | `ErasureTargetOut` | yes | — |

### `ErasureLedgerPageOut`

A page of the erasure ledger, newest first, with a cursor.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `ErasureLedgerEntryOut` | yes | — |
| `next_before` | `integer` or `null` | yes | — |

### `ErasureReportOut`

The result of an erasure -- with the tombstone, never the identifier.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | `string` | yes | — |
| `tombstone` | `string` | yes | — |
| `at` | `string (date-time)` | yes | — |
| `targets` | `ErasureTargetOut` | yes | — |
| `preserved` | `PreservedLedgerOut` | yes | — |
| `already_erased` | `boolean` | yes | — |
| `ledger_sequence` | `integer` or `null` | yes | — |
| `affected` | `integer` | yes | — |
| `reason` | `string` | no | — |

### `ErasureRequest`

An erasure request. The only model here that carries the subject's value.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | `string` | yes | 'user' (an account) or 'entity' (an observed host, service or address). |
| `value` | `string` | yes | The identifier to erase. |
| `reason` | `string` | no | Why the request was made. Recorded; never an identifier. |

### `ErasureTargetOut`

What one store did.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` | yes | — |
| `affected` | `integer` | yes | — |

### `EvidenceOccurrenceOut`

One window in the evidence trail behind an alert.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `string` | yes | The window's stable identity, as T-307 emitted it. |
| `modality` | `string` | yes | Which model scored the window: flow or log. |
| `score` | `number` | yes | That model's score for the window, in [0, 1]. |
| `at` | `string (date-time)` | yes | When the window closed, timezone-aware UTC. |
| `model` | `string` or `null` | no | The version that scored it. |
| `expires_at` | `string (date-time)` | yes | When FR-05's raw-record window takes this evidence away. |
| `expired` | `boolean` | yes | True once the raw records behind it are gone. |

### `EvidenceOut`

design.md §4.3's zone 3: the raw records behind the alert.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `window_id` | `string` or `null` | no | The window the case opened on, when recorded. |
| `trace_id` | `string` or `null` | no | Trace of the ingest request that opened the case (T-317). |
| `grouped` | `boolean` | no | True when the correlator fused several detections into one case. |
| `occurrences` | `EvidenceOccurrenceOut` | no | — |
| `retention_days` | `integer` | yes | FR-05's raw-record window the expiry dates above are computed from. |
| `expired` | `boolean` | no | True when every occurrence is past retention. |
| `unreadable` | `integer` | no | Trail entries that could not be decoded, reported rather than dropped. |
| `note` | `string` or `null` | no | Why the trail is incomplete, in the operator's words. |

### `ExplanationOut`

R-70's explanation contract, as the alert row stored it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `reasons` | list of `string` | no | Rendered reasons, most contributory first. |
| `unavailable` | `boolean` | no | True when no explanation could be produced (R-70). |
| `detail` | `string` or `null` | no | Why it is unavailable. Never a stack trace (R-58). |
| `unavailable_modalities` | list of `string` | no | Modalities that contributed without reasons. |
| `partial_evidence` | `boolean` | no | True while only one modality has contributed. |
| `families` | list of `string` | no | Every family the case's occurrences named. |

### `FamilyHistoryOut`

The trust hint: what analysts decided about this entity and family before.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `family` | `string` | yes | — |
| `window_days` | `integer` | yes | How far back the counts reach. |
| `prior_alerts` | `integer` | no | Alerts on this entity and family before this one. |
| `labelled` | `integer` | no | How many of them carry a verdict at all. |
| `false_positive` | `integer` | no | — |
| `benign` | `integer` | no | — |
| `true_positive` | `integer` | no | — |

### `FlowRecordIn`

One flow record on the wire — the ``flow@1`` contract.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | `string` | no | — |
| `timestamp` | `string (date-time)` | yes | — |
| `src_ip` | `string (ipv4)` | yes | — |
| `dst_ip` | `string (ipv4)` | yes | — |
| `src_port` | `integer` | yes | — |
| `dst_port` | `integer` | yes | — |
| `protocol` | `Protocol` | yes | — |
| `direction` | `Direction` | yes | — |
| `service` | `string` or `null` | no | — |
| `state` | `string` or `null` | no | — |
| `packets` | `integer` | yes | — |
| `src_packets` | `integer` | yes | — |
| `dst_packets` | `integer` | yes | — |
| `src_bytes` | `integer` | yes | — |
| `dst_bytes` | `integer` | yes | — |
| `duration` | `number` | yes | — |
| `syn` | `integer` | no | — |
| `ack` | `integer` | no | — |
| `rst` | `integer` | no | — |
| `fin` | `integer` | no | — |
| `psh` | `integer` | no | — |
| `urg` | `integer` | no | — |
| `label` | `string` or `null` | no | — |

### `HTTPValidationError`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `detail` | `ValidationError` | no | — |

### `HealthResponse`

Liveness: the process is running. Never reflects dependency state.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `status` | `string` | yes | Always 'ok' when the process is up. |
| `service` | `string` | yes | Service name, e.g. aegis-backend. |
| `version` | `string` | yes | Build version of the running artifact. |
| `environment` | `string` | yes | Deployment environment. |

### `IngestResponse`

The outcome of a batch. Nothing accepted or rejected goes unreported.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `received` | `integer` | yes | — |
| `accepted` | `integer` | yes | — |
| `rejected` | `integer` | yes | — |
| `errors` | `RecordError` | no | — |

### `LogLevel`

Severity levels ``log@1`` recognises.

Types: `debug` or `info` or `warning` or `error` or `critical`.

### `LogRecordIn`

One log line on the wire — the ``log@1`` contract.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | `string` | no | — |
| `timestamp` | `string (date-time)` | yes | — |
| `host` | `string` | yes | — |
| `service` | `string` | yes | — |
| `level` | `LogLevel` | yes | — |
| `message` | `string` | yes | — |
| `template_id` | `string` or `null` | no | — |
| `parameters` | map of string to `string` | no | — |
| `label` | `string` or `null` | no | — |

### `MetricPointOut`

A metric value beside the run it came from (R-74).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `value` | `number` | yes | — |
| `artifact` | `string` | yes | Path or id of the recorded run the value was read from. |
| `field` | `string` | yes | Location of the value inside that artifact. |

### `ModelListOut`

The registered versions, in the order the version table renders them.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `ModelOut` | yes | — |
| `count` | `integer` | yes | — |

### `ModelMetricsOut`

FR-31's metrics for one version, on a named split.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `split` | `string` | yes | The split these numbers were measured on, e.g. 'temporal:2025-Q4'. |
| `evaluated_at` | `string (date-time)` | yes | — |
| `metrics` | map of string to `MetricPointOut` | yes | — |

### `ModelOut`

One registered model version.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `model_id` | `string` | yes | — |
| `kind` | `string` | yes | — |
| `status` | `string` | yes | — |
| `artifact_uri` | `string` | yes | — |
| `sha256` | `string` | yes | — |
| `manifest_present` | `boolean` | yes | Whether a training_manifest.json ships with it. False means R-63 refuses its promotion. |
| `metrics` | `ModelMetricsOut` or `null` | no | — |
| `promoted_at` | `string (date-time)` or `null` | no | — |
| `promoted_by` | `string` or `null` | no | — |
| `justification` | `string` | no | — |

### `ModelTransitionOut`

What a promotion or rollback did.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `model_id` | `string` | yes | — |
| `kind` | `string` | yes | — |
| `status` | `string` | yes | — |
| `retired` | `string` or `null` | yes | — |
| `changed` | `boolean` | yes | — |
| `at` | `string (date-time)` | yes | — |
| `actor` | `string` | yes | — |

### `PreservedLedgerOut`

An append-only store the erasure did not rewrite, and why.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` | yes | — |
| `reason` | `string` | yes | — |

### `ProbeCheck`

Result of one registered readiness probe.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` | yes | — |
| `status` | `ok` or `degraded` or `unavailable` | yes | — |
| `detail` | `string` | no | — |

### `PromotionRequest`

A request to make a version active.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `justification` | `string` | yes | — |

### `Protocol`

Transport protocols ``flow@1`` recognises.

Types: `tcp` or `udp` or `icmp`.

### `ReadinessResponse`

Readiness: can this process serve traffic right now?

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `status` | `ready` or `not_ready` | yes | — |
| `service` | `string` | yes | — |
| `version` | `string` | yes | — |
| `checks` | `ProbeCheck` | no | One entry per registered dependency. Empty in the S0 skeleton. |

### `RecalibrationOut`

A run's report: the window it read, and every threshold it considered.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `tenant_id` | `string` | yes | — |
| `band` | `string` | yes | — |
| `at` | `string (date-time)` | yes | — |
| `since` | `string (date-time)` | yes | — |
| `until` | `string (date-time)` | yes | — |
| `quantile` | `number` | yes | — |
| `minimum_sample` | `integer` | yes | — |
| `considered` | `integer` | yes | — |
| `changed` | `integer` | yes | — |
| `outcomes` | `ThresholdOutcomeOut` | yes | — |

### `RecalibrationRequest`

Which band to recalibrate. Everything else is policy, not a per-run knob.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `band` | `string` | no | FR-13 band whose lower bound to move. `high` is the default because the PRD measures precision and recall at the deployed `high` threshold, so that is the bar a false-positive budget applies to. |

### `RecordError`

Why one record in a batch was rejected (FR-04).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `index` | `integer` | yes | — |
| `stage` | `parse` or `validation` | yes | — |
| `message` | `string` | yes | — |
| `field` | `string` or `null` | no | — |

### `RelatedAlertsOut`

Other alerts on the same entity around this one, for §4.3's "Related alerts".

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `window_minutes` | `integer` | yes | Half-width of the window searched, in minutes. |
| `items` | `AlertRow` | no | — |
| `truncated` | `boolean` | no | True when more related alerts exist than were returned. |

### `RetentionPlanOut`

What a retention run would do, now.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `planned_at` | `string (date)` | yes | — |
| `policy` | `RetentionPolicyOut` | yes | — |
| `drop` | `DroppedPartitionOut` | yes | — |
| `kept` | `DroppedPartitionOut` | yes | — |
| `missing` | list of `string` | yes | — |
| `unevictable` | `UnevictableOut` | yes | — |
| `external` | map of string to `string` | yes | — |
| `statements` | list of `string` | yes | — |

### `RetentionPolicyOut`

The windows a deployment retains each class of data.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `raw_records_days` | `integer` | yes | — |
| `alerts_days` | `integer` | yes | — |
| `stats_days` | `integer` | yes | — |

### `RetentionRunOut`

What a retention run did, including how much of it was already done.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `started_at` | `string (date-time)` | yes | — |
| `planned` | list of `string` | yes | — |
| `dropped` | list of `string` | yes | — |
| `already_absent` | list of `string` | yes | — |
| `changed_anything` | `boolean` | yes | — |

### `RollbackRequest`

A request to reverse the most recent promotion of a kind.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `reason` | `string` | yes | — |

### `ScopeListOut`

The scopes a key may be issued with, and what each one grants.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `ScopeOut` | yes | — |

### `ScopeOut`

One scope, with the capabilities it grants.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | `string` | yes | — |
| `capabilities` | list of `string` | yes | — |

### `ThresholdListOut`

The values in force for this deployment, and the defaults behind them.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `tenant_id` | `string` | yes | — |
| `defaults` | map of string to `number` | yes | FR-13's documented initial band edges, in force wherever no row exists. |
| `items` | `ThresholdOut` | yes | — |

### `ThresholdOut`

One ``thresholds`` row, as the API returns it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `tenant_id` | `string` | yes | — |
| `family` | `string` | yes | — |
| `band` | `string` | yes | — |
| `value` | `number` | yes | — |
| `source` | `string` | yes | — |
| `updated_at` | `string (date-time)` | yes | — |

### `ThresholdOutcomeOut`

What the run decided about one threshold.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `family` | `string` | yes | — |
| `band` | `string` | yes | — |
| `previous` | `number` | yes | — |
| `previous_was_default` | `boolean` | yes | — |
| `requested` | `number` or `null` | yes | — |
| `applied` | `number` | yes | — |
| `changed` | `boolean` | yes | — |
| `clamped` | `boolean` | yes | — |
| `sample_size` | `integer` | yes | — |
| `reason` | `string` | yes | `fitted` or `insufficient_feedback`. |

### `UnevictableOut`

A table retention will not touch, and the reason in one sentence.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `table` | `string` | yes | — |
| `reason` | `string` | yes | — |

### `ValidationError`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `loc` | list of `string` or `integer` | yes | — |
| `msg` | `string` | yes | — |
| `type` | `string` | yes | — |
| `input` | `any` | no | — |
| `ctx` | `object` | no | — |

### `VerdictHistoryOut`

Every verdict recorded on one alert, oldest first.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `alert_id` | `integer` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `current` | `VerdictRecordOut` or `null` | yes | — |
| `items` | `VerdictRecordOut` | yes | — |

### `VerdictOutcomeOut`

The result of recording a verdict.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | `string` | yes | — |
| `record` | `VerdictRecordOut` | yes | — |
| `superseded` | `VerdictRecordOut` or `null` | yes | — |

### `VerdictRecordOut`

One verdict record as returned by the API.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `string` | yes | — |
| `alert_id` | `integer` | yes | — |
| `verdict` | `string` | yes | — |
| `actor` | `string` | yes | — |
| `at` | `string (date-time)` | yes | — |
| `note` | `string` or `null` | yes | — |
| `supersedes` | `string` or `null` | yes | — |

### `VerdictRequest`

A verdict to record on one alert.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `verdict` | `string` | yes | true_positive, false_positive or benign. |
| `created_at` | `string (date-time)` | yes | The alert's created_at, which addresses its partition (D-030). |
| `note` | `string` or `null` | no | — |

### `WebhookCreate`

A webhook target to register.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `url` | `string` | yes | https:// destination. |
| `description` | `string` or `null` | no | — |
| `severity_floor` | `string` | no | Lowest severity delivered: info, low, medium, high or critical. |

### `WebhookCreatedOut`

A newly registered target, with its secret shown exactly once.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `string` | yes | — |
| `url` | `string` | yes | — |
| `description` | `string` or `null` | yes | — |
| `severity_floor` | `string` | yes | — |
| `active` | `boolean` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
| `secret` | `string` | yes | Signing secret. Shown once; store it now. |

### `WebhookListOut`

Every configured target.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | `WebhookOut` | yes | — |

### `WebhookOut`

A configured target, **without** its secret.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `string` | yes | — |
| `url` | `string` | yes | — |
| `description` | `string` or `null` | yes | — |
| `severity_floor` | `string` | yes | — |
| `active` | `boolean` | yes | — |
| `created_at` | `string (date-time)` | yes | — |
